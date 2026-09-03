import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.models import Account, AppSettings, ProxyPool, RegisterTask
from backend.app.schemas.settings import SmsSettings
from backend.app.schemas.register import RegisterConfig, RegisterProgress
from backend.app.services.browser.bitbrowser_controller import BitBrowserController
from backend.app.services.browser.patchright_controller import PatchrightController
from backend.app.services.browser.playwright_controller import PlaywrightController
from backend.app.services.browser.utils import generate_strong_password, random_email
from backend.app.services.event_bus import EventBus
from backend.app.core.config import get_settings
from backend.app.services.secret_store import PlaintextSecretStore
from backend.app.services.sms_provider import SmsConfig, SmsService

secret_store = PlaintextSecretStore()


class RegisterService:
    """
    批量注册服务
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.active_tasks: dict[int, bool] = {}

    def _get_oauth2_settings(self, session: Session) -> dict:
        """
        获取OAuth2设置
        """
        settings = session.scalar(select(AppSettings))
        if settings:
            scopes = json.loads(settings.oauth2_scopes) if settings.oauth2_scopes else []
            return {
                "client_id": settings.oauth2_client_id,
                "redirect_url": settings.oauth2_redirect_url,
                "scopes": scopes
            }
        return {"client_id": "", "redirect_url": "", "scopes": []}

    def _get_random_proxy(self, session: Session) -> str | None:
        """
        获取随机代理
        """
        import random
        proxies = session.scalars(
            select(ProxyPool).where(ProxyPool.is_enabled == True)
        ).all()

        if not proxies:
            return None

        proxy = random.choice(proxies)
        proxy.last_used_at = datetime.utcnow()
        session.commit()

        return proxy.proxy_url

    def _create_account(self, session: Session, email: str, password: str, client_id: str = "", refresh_token: str = "") -> Account:
        """
        创建账号
        """
        full_email = f"{email}@outlook.com"
        domain = "outlook.com"

        account = session.scalar(select(Account).where(Account.email == full_email))
        if account:
            account.password = secret_store.store(password)
            account.client_id = secret_store.store(client_id)
            account.refresh_token = secret_store.store(refresh_token)
            account.access_token = None
            account.access_token_expires_at = None
            account.account_status = "disconnected"
            account.last_error = None
            account.updated_at = datetime.utcnow()
        else:
            account = Account(
                email=full_email,
                domain=domain,
                password=secret_store.store(password),
                client_id=secret_store.store(client_id),
                refresh_token=secret_store.store(refresh_token),
                account_status="disconnected"
            )
            session.add(account)

        session.commit()
        session.refresh(account)
        return account

    def _run_single_register(
        self,
        config: RegisterConfig,
        proxy: str | None,
        oauth2_settings: dict,
        sms_service=None
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        执行单个注册流程
        """
        browser_config = {
            "bot_protection_wait": config.bot_protection_wait,
            "max_captcha_retries": config.max_captcha_retries,
            "enable_oauth2": config.enable_oauth2,
            "proxy": proxy or get_settings().clash_proxy,
            "sms_service": sms_service,
        }

        if config.browser == "bitbrowser":
            controller = BitBrowserController(browser_config)
        elif config.browser == "patchright":
            controller = PatchrightController(browser_config)
        else:
            controller = PlaywrightController(browser_config)

        page = None
        try:
            page = controller.get_thread_page()
            email = random_email()
            password = generate_strong_password()

            success, message = controller.outlook_register(page, email, password)

            if not success:
                return False, message, {"email": f"{email}@outlook.com"}

            client_id = ""
            refresh_token = ""

            if config.enable_oauth2 and oauth2_settings.get("client_id"):
                token_result = self._get_oauth2_token(
                    page, email, oauth2_settings, password
                )
                if token_result:
                    refresh_token, client_id = token_result

            with SessionLocal() as session:
                self._create_account(
                    session, email, password,
                    client_id or oauth2_settings.get("client_id", ""),
                    refresh_token
                )

            message = "注册成功"
            if config.enable_oauth2 and not refresh_token:
                message = "注册成功，但OAuth2 Token获取失败"

            return True, message, {
                "email": f"{email}@outlook.com",
                "password": password
            }

        except Exception as e:
            return False, str(e), {}
        finally:
            controller.clean_up(page, "done_browser")

    def _get_oauth2_token(self, page, email: str, oauth2_settings: dict, password: str = "") -> tuple[str, str] | None:
        """
        OAuth2 authorization code flow (PKCE) for consumer MSA accounts.
        Uses consumers tenant -> redirects to login.live.com for MSA auth.
        """
        import base64, hashlib, secrets, string
        from urllib.parse import quote, parse_qs
        import requests

        def gen_cv(length=128):
            return ''.join(secrets.choice(string.ascii_letters + string.digits + '-._~') for _ in range(length))

        def gen_cc(cv):
            return base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip('=')

        try:
            client_id = oauth2_settings["client_id"]
            redirect_url = oauth2_settings["redirect_url"]
            scopes = oauth2_settings.get("scopes", [])
            cv = gen_cv()
            params = {
                'client_id': client_id, 'response_type': 'code', 'redirect_uri': redirect_url,
                'scope': ' '.join(scopes), 'response_mode': 'query', 'prompt': 'consent',
                'code_challenge': gen_cc(cv), 'code_challenge_method': 'S256',
            }

            captured = {"code": None}

            def handle_redirect(route):
                u = route.request.url
                if "code=" in u and "?" in u:
                    c = parse_qs(u.split("?")[1])
                    if "code" in c:
                        captured["code"] = c["code"][0]
                route.fulfill(body="ok", status=200)

            page.route("http://localhost/*", handle_redirect)

            # Use /consumers/ tenant which redirects to login.live.com for MSA accounts
            url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?" + "&".join(f"{k}={quote(v)}" for k, v in params.items())
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            auth_code = captured["code"]

            # ----- Step 1: fill email on login.live.com (uses #usernameEntry) -----
            if not auth_code:
                try:
                    email_input = page.locator('#usernameEntry')
                    if email_input.count() > 0:
                        email_input.first.fill(f"{email}@outlook.com", timeout=8000)
                        page.wait_for_timeout(1000)
                        next_btn = page.locator('button[type="submit"]')
                        if next_btn.count() > 0:
                            next_btn.first.click(timeout=8000)
                            page.wait_for_timeout(5000)
                except Exception:
                    pass

            # ----- Step 2: fill password on login.live.com -----
            if not auth_code and password:
                try:
                    pw_input = page.locator('#passwordEntry, input[type="password"]')
                    if pw_input.count() > 0:
                        pw_input.first.fill(password, timeout=8000)
                        page.wait_for_timeout(1000)
                        signin_btn = page.locator('button[type="submit"]')
                        if signin_btn.count() > 0:
                            signin_btn.first.click(timeout=8000)
                            page.wait_for_timeout(5000)
                except Exception:
                    pass

            # ----- Step 3: handle "Stay signed in?" prompt ("No" / "Don't show again") -----
            if not auth_code:
                try:
                    for sel in ['input[value="No"]', '#declineButton',
                                 'button:has-text("No")', 'button:has-text("Don\'t show")']:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click(timeout=5000)
                            page.wait_for_timeout(3000)
                            break
                except Exception:
                    pass

            # ----- Step 4: click consent on live.com (may use "Yes" button) -----
            if not auth_code:
                try:
                    for sel in ['[data-testid="appConsentPrimaryButton"]',
                                 'input[value="Accept"]', 'input[value="接受"]',
                                 'input[value="Yes"]', 'button:has-text("Yes")',
                                 'button:has-text("Accept")']:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click(timeout=8000)
                            page.wait_for_timeout(4000)
                            break
                except Exception:
                    pass

            # ----- Wait and capture code -----
            page.wait_for_timeout(5000)
            auth_code = captured["code"] or auth_code
            if not auth_code and "code=" in page.url:
                auth_code = parse_qs(page.url.split("?")[1])["code"][0]

            if not auth_code:
                return None

            # ----- Exchange code for tokens -----
            token_data = {
                "client_id": client_id, "code": auth_code, "redirect_uri": redirect_url,
                "grant_type": "authorization_code", "code_verifier": cv,
                "scope": " ".join(scopes),
            }
            resp = requests.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30,
            )
            if resp.ok and "refresh_token" in resp.json():
                return resp.json()["refresh_token"], client_id
            return None

        except Exception as e:
            return None

    async def start_task(self, config: RegisterConfig) -> int:
        """
        启动注册任务
        """
        with SessionLocal() as session:
            task = RegisterTask(
                status="pending",
                total_count=config.max_tasks,
                config=json.dumps(config.model_dump())
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        self.active_tasks[task_id] = True

        asyncio.create_task(self._run_task(task_id, config))

        return task_id

    async def _run_task(self, task_id: int, config: RegisterConfig):
        """
        运行注册任务
        """
        with SessionLocal() as session:
            task = session.scalar(select(RegisterTask).where(RegisterTask.id == task_id))
            if not task:
                return

            task.status = "running"
            session.commit()

        oauth2_settings = {}
        sms_service = None
        with SessionLocal() as session:
            oauth2_settings = self._get_oauth2_settings(session)
            settings = session.scalar(select(AppSettings))
            if settings and settings.sms_api_key:
                sms_config = SmsConfig(
                    provider=settings.sms_provider or "5sim",
                    api_key=settings.sms_api_key,
                    country=settings.sms_country or "Indonesia",
                    operator=settings.sms_operator or "any",
                )
                try:
                    sms_service = SmsService(sms_config)
                    bal = sms_service.get_balance()
                    self.event_bus.emit("register_progress", {
                        "type": "sms_balance", "balance": bal
                    })
                except Exception as e:
                    sms_service = None

        succeeded = 0
        failed = 0
        current = 0

        loop = asyncio.get_event_loop()

        def run_register():
            with SessionLocal() as session:
                proxy = self._get_random_proxy(session)

            return self._run_single_register(config, proxy, oauth2_settings, sms_service)

        # 任务级线程池：整个任务期间复用同一个线程池，减少创建/销毁开销
        with ThreadPoolExecutor(max_workers=config.concurrent_flows) as executor:
            while current < config.max_tasks and self.active_tasks.get(task_id, False):
                futures = []
                batch_size = min(config.concurrent_flows, config.max_tasks - current)

                for _ in range(batch_size):
                    if not self.active_tasks.get(task_id, False):
                        break
                    futures.append(loop.run_in_executor(executor, run_register))

                for future in futures:
                    if not self.active_tasks.get(task_id, False):
                        break

                    try:
                        success, message, data = await future
                        current += 1

                        if success:
                            succeeded += 1
                        else:
                            failed += 1

                        progress = RegisterProgress(
                            task_id=task_id,
                            current=current,
                            total=config.max_tasks,
                            succeeded=succeeded,
                            failed=failed,
                            latest_email=data.get("email"),
                            latest_status="success" if success else "failed",
                            message=message
                        )
                        self.event_bus.emit("register_progress", progress.model_dump())

                    except Exception as e:
                        current += 1
                        failed += 1

                await asyncio.sleep(0.5)

        with SessionLocal() as session:
            task = session.scalar(select(RegisterTask).where(RegisterTask.id == task_id))
            if task:
                task.status = "completed"
                task.succeeded_count = succeeded
                task.failed_count = failed
                task.completed_at = datetime.utcnow()
                session.commit()

        self.active_tasks.pop(task_id, None)

    async def get_task_status(self, task_id: int) -> dict | None:
        """
        获取任务状态
        """
        with SessionLocal() as session:
            task = session.scalar(select(RegisterTask).where(RegisterTask.id == task_id))
            if not task:
                return None

            return {
                "id": task.id,
                "status": task.status,
                "total_count": task.total_count,
                "succeeded_count": task.succeeded_count,
                "failed_count": task.failed_count,
                "created_at": task.created_at,
                "completed_at": task.completed_at
            }

    async def cancel_task(self, task_id: int) -> bool:
        """
        取消任务
        """
        if task_id in self.active_tasks:
            self.active_tasks[task_id] = False

            with SessionLocal() as session:
                task = session.scalar(select(RegisterTask).where(RegisterTask.id == task_id))
                if task:
                    task.status = "cancelled"
                    task.completed_at = datetime.utcnow()
                    session.commit()

            return True

        return False
