import json
import urllib.error
import urllib.request

from backend.app.services.browser.base_controller import BaseBrowserController


class BitBrowserController(BaseBrowserController):
    """
    BitBrowser controller using the local BitBrowser API and Playwright CDP.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_url = config.get("bitbrowser_api_url") or "http://127.0.0.1:54345"
        self.browser_id = config.get("bitbrowser_id") or ""
        self.created_browser_ids: list[str] = []

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"BitBrowser API request failed: {exc}") from exc

    def _ensure_browser_id(self) -> str:
        if self.browser_id:
            return self.browser_id

        payload = {
            "name": "outlook-batch-manager",
            "remark": "Created by outlook-batch-manager",
            "proxyMethod": 2,
            "proxyType": "noproxy",
            "host": "",
            "port": "",
            "proxyUserName": "",
            "proxyPassword": "",
            "browserFingerPrint": {
                "coreVersion": "130",
            },
        }
        if self.proxy:
            payload.update(self._parse_proxy(self.proxy))

        res = self._post("/browser/update", payload)
        if not res.get("success") or not res.get("data", {}).get("id"):
            raise RuntimeError(f"BitBrowser profile creation failed: {res.get('msg') or res}")

        browser_id = res["data"]["id"]
        self.browser_id = browser_id
        self.created_browser_ids.append(browser_id)
        return browser_id

    def _parse_proxy(self, proxy: str) -> dict:
        from urllib.parse import urlparse

        parsed = urlparse(proxy)
        proxy_type = parsed.scheme or "http"
        return {
            "proxyType": proxy_type,
            "host": parsed.hostname or "",
            "port": str(parsed.port or ""),
            "proxyUserName": parsed.username or "",
            "proxyPassword": parsed.password or "",
        }

    def launch_browser(self):
        from playwright.sync_api import sync_playwright

        browser_id = self._ensure_browser_id()
        res = self._post("/browser/open", {"id": browser_id})
        if not res.get("success"):
            raise RuntimeError(f"BitBrowser open failed: {res.get('msg') or res}")

        endpoint = res.get("data", {}).get("ws") or res.get("data", {}).get("http")
        if not endpoint:
            raise RuntimeError(f"BitBrowser open response did not include CDP endpoint: {res}")

        p = sync_playwright().start()
        b = p.chromium.connect_over_cdp(endpoint if endpoint.startswith("http") or endpoint.startswith("ws") else f"http://{endpoint}")
        return p, b

    def get_thread_page(self):
        browser = self.get_thread_browser()
        if not browser:
            raise RuntimeError("Failed to launch BitBrowser")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return context.new_page()

    def handle_captcha(self, page):
        page.wait_for_timeout(1000)
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

        challenge_markers = ("证明你不是机器人", "长按该按钮", "prove you are not a robot", "hold this button")
        if not any(marker.lower() in body_text.lower() for marker in challenge_markers):
            return True

        try:
            page.wait_for_function(
                """
                () => {
                  const text = document.body?.innerText?.toLowerCase() || "";
                  return !text.includes("证明你不是机器人")
                    && !text.includes("长按该按钮")
                    && !text.includes("prove you are not a robot")
                    && !text.includes("hold this button");
                }
                """,
                timeout=180000,
            )
            page.wait_for_timeout(3000)
            return True
        except Exception:
            return False

    def clean_up(self, page=None, type="all_browser"):
        if page:
            try:
                page.close()
            except Exception:
                pass

        for p, b in self.active_resources:
            try:
                b.close()
            except Exception:
                pass
            try:
                p.stop()
            except Exception:
                pass

        for browser_id in self.created_browser_ids:
            try:
                self._post("/browser/close", {"id": browser_id})
            except Exception:
                pass
