import random
import time

from backend.app.services.browser.base_controller import BaseBrowserController


class PatchrightController(BaseBrowserController):

    def launch_browser(self):
        try:
            from patchright.sync_api import sync_playwright

            p = sync_playwright().start()

            proxy_settings = {
                "server": self.proxy,
                "bypass": "localhost",
            } if self.proxy else None

            b = p.chromium.launch(
                headless=False,
                args=['--lang=zh-CN'],
                proxy=proxy_settings
            )

            return p, b

        except Exception:
            return False, False

    def handle_captcha(self, page):
        for _ in range(self.max_captcha_retries + 2):
            try:
                frame = self._find_captcha_frame(page)
                if not frame:
                    page.wait_for_timeout(2000)
                    continue

                btn = frame.locator('[aria-label="可访问性挑战"], [aria-label*="press"], [aria-label*="按住"]')
                if btn.count() > 0:
                    btn.click(timeout=5000)
                    page.wait_for_timeout(1500)

                hold = frame.locator('[aria-label="再次按下"], [aria-label*="hold"], [aria-label*="按住"]')
                if hold.count() > 0:
                    hold.click(timeout=5000)
                    page.wait_for_timeout(2000)

                page.wait_for_timeout(4000)

                if page.locator('.draw').count() == 0 or page.get_by_text("取消").count() > 0:
                    return True

            except Exception:
                page.wait_for_timeout(2000)

            try:
                page.get_by_text("请再试一次").wait_for(timeout=8000)
            except Exception:
                if page.get_by_text("取消").count() > 0 or page.locator('.draw').count() == 0:
                    return True

        return True

    def _find_captcha_frame(self, page):
        selectors = [
            'iframe[title="验证质询"]',
            'iframe[title*="captcha"]',
            'iframe[title*="challenge"]',
            'iframe[id="enforcementFrame"]',
            'iframe[src*="captcha"]',
        ]
        for sel in selectors:
            frames = page.frame_locator(sel)
            try:
                inner = frames.frame_locator('iframe')
                if inner.count() > 0:
                    return inner
            except Exception:
                pass
            try:
                if frames.count() > 0:
                    return frames
            except Exception:
                pass
        return None

    def get_thread_page(self):
        browser = self.get_thread_browser()
        if not browser:
            raise RuntimeError("Failed to launch browser")
        context = browser.new_context()
        return context.new_page()

    def clean_up(self, page=None, type="all_browser"):
        if type == "done_browser" and page:
            context = page.context
            context.close()

        elif type == "all_browser":
            for p, b in self.active_resources:
                try:
                    b.close()
                except Exception:
                    pass
                try:
                    p.stop()
                except Exception:
                    pass
