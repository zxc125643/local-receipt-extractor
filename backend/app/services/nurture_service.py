import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.models import Account
from backend.app.services.browser.patchright_controller import PatchrightController
from backend.app.services.secret_store import PlaintextSecretStore

secret_store = PlaintextSecretStore()

NURTURE_STAGES = {
    0: "pending",
    1: "day1_login",
    2: "day2_3_send",
    3: "day4_7_normal",
    4: "matured",
}

STAGE_INTERVALS = {
    0: timedelta(hours=0),
    1: timedelta(hours=2),
    2: timedelta(days=2),
    3: timedelta(days=4),
    4: timedelta(days=7),
}


class NurtureService:

    def __init__(self):
        self._running = {}

    def get_nurture_candidates(self, session: Session, limit: int = 5) -> list[Account]:
        now = datetime.utcnow()
        return list(session.scalars(
            select(Account).where(
                Account.nurture_status.in_(["pending", "running"]),
                Account.nurture_stage < 4,
                (Account.nurture_next_at == None) | (Account.nurture_next_at <= now),
            ).order_by(Account.nurture_next_at.asc().nullsfirst())
            .limit(limit)
        ))

    def run_nurture_cycle(self, account: Account) -> tuple[bool, str]:
        password = secret_store.reveal(account.password)
        controller = PatchrightController({
            "bot_protection_wait": 6,
            "max_captcha_retries": 2,
            "enable_oauth2": False,
            "proxy": "",
        })
        page = None
        try:
            page = controller.get_thread_page()
            success, msg = self._login_outlook(page, account.email, password)
            if not success:
                return False, f"login failed: {msg}"

            stage = account.nurture_stage
            if stage == 0:
                result = self._stage_welcome(page, account)
            elif stage == 1:
                result = self._stage_send_emails(page, account)
            elif stage == 2:
                result = self._stage_normal_use(page, account)
            elif stage == 3:
                result = self._stage_mature(page, account)
            else:
                result = (True, "already matured")

            return result

        except Exception as e:
            return False, str(e)
        finally:
            controller.clean_up(page, "all_browser")

    def _login_outlook(self, page, email: str, password: str) -> tuple[bool, str]:
        try:
            page.goto("https://outlook.live.com/mail/", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            signin_btn = page.locator('[data-task="signin"]')
            if signin_btn.count() > 0:
                signin_btn.click(timeout=10000)
                page.wait_for_timeout(2000)

            page.locator('[name="loginfmt"]').fill(email, timeout=15000)
            page.locator('#idSIButton9').click(timeout=10000)
            page.wait_for_timeout(2000)

            page.locator('[name="passwd"]').fill(password, timeout=15000)
            page.locator('#idSIButton9').click(timeout=10000)
            page.wait_for_timeout(3000)

            stay_btn = page.locator('#idBtn_Back')
            if stay_btn.count() > 0:
                stay_btn.click(timeout=5000)
                page.wait_for_timeout(3000)

            page.wait_for_timeout(5000)
            return True, "logged in"
        except Exception as e:
            return False, str(e)

    def _stage_welcome(self, page, account: Account) -> tuple[bool, str]:
        actions = 0
        try:
            welcome = page.get_by_text("Welcome", exact=False)
            if welcome.count() > 0:
                welcome.first.click(timeout=5000)
                page.wait_for_timeout(3000)
                actions += 1

            unread = page.locator('[aria-label*="unread"], [class*="unread"]').first
            if unread.count() > 0:
                unread.click(timeout=5000)
                page.wait_for_timeout(5000)
                actions += 1

            page.wait_for_timeout(random.randint(5000, 15000))
            self._advance_stage(account)
            return True, f"welcome done, {actions} actions"
        except Exception as e:
            self._advance_stage(account)
            return True, f"welcome partial: {e}"

    def _stage_send_emails(self, page, account: Account) -> tuple[bool, str]:
        actions = 0
        try:
            new_msg = page.locator('[aria-label*="New message"], [aria-label*="新建"], [data-testid*="newMessage"]')
            if new_msg.count() == 0:
                new_msg = page.locator('a[title*="新邮件"], button[title*="新邮件"]')
            if new_msg.count() == 0:
                new_msg = page.locator('span:has-text("新邮件")')
            if new_msg.count() > 0:
                new_msg.first.click(timeout=10000)
                page.wait_for_timeout(3000)

                to_input = page.locator('[aria-label*="To"], [aria-label*="收件人"], input[role="combobox"]')
                if to_input.count() > 0:
                    to_input.fill(account.email, timeout=5000)
                    page.wait_for_timeout(1000)

                subject = page.locator('[aria-label*="Subject"], [aria-label*="主题"], input[role="textbox"]')
                if subject.count() > 0:
                    subject.fill(f"test {datetime.utcnow().strftime('%Y%m%d%H%M')}", timeout=5000)
                    page.wait_for_timeout(1000)

                body = page.locator('[aria-label*="Message body"], [role="textbox"][aria-multiline="true"]')
                if body.count() > 0:
                    body.fill(f"Hello from automated test\n\nSent at: {datetime.utcnow()}", timeout=5000)
                    page.wait_for_timeout(2000)

                send_btn = page.locator('[aria-label*="Send"], button[title*="发送"], [data-testid*="send"]')
                if send_btn.count() > 0:
                    send_btn.first.click(timeout=10000)
                    page.wait_for_timeout(5000)
                    actions += 1

            page.wait_for_timeout(random.randint(5000, 15000))
            self._advance_stage(account)
            return True, f"sent {actions} emails"
        except Exception as e:
            return False, f"send failed: {e}"

    def _stage_normal_use(self, page, account: Account) -> tuple[bool, str]:
        actions = 0
        try:
            settings = page.locator('[aria-label*="Settings"], [data-testid*="settings"]')
            if settings.count() > 0:
                settings.first.click(timeout=5000)
                page.wait_for_timeout(2000)

            page.wait_for_timeout(random.randint(5000, 20000))
            self._advance_stage(account)
            return True, f"normal use done, {actions} actions"
        except Exception as e:
            self._advance_stage(account)
            return True, f"normal partial: {e}"

    def _stage_mature(self, page, account: Account) -> tuple[bool, str]:
        page.wait_for_timeout(random.randint(10000, 30000))
        with SessionLocal() as session:
            db = session.scalar(select(Account).where(Account.id == account.id))
            if db:
                db.nurture_status = "completed"
                db.nurture_next_at = datetime.utcnow() + timedelta(days=30)
                session.commit()
        return True, "account matured"

    def _advance_stage(self, account: Account):
        with SessionLocal() as session:
            db = session.scalar(select(Account).where(Account.id == account.id))
            if db:
                db.nurture_stage += 1
                db.nurture_count = (db.nurture_count or 0) + 1
                interval = STAGE_INTERVALS.get(db.nurture_stage, timedelta(days=1))
                db.nurture_next_at = datetime.utcnow() + interval
                db.nurture_status = "running"
                session.commit()

    def schedule_next(self, session: Session, account: Account):
        account.nurture_next_at = datetime.utcnow() + STAGE_INTERVALS.get(
            account.nurture_stage, timedelta(days=1)
        )
        session.commit()
