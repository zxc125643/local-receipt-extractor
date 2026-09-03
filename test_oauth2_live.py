from patchright.sync_api import sync_playwright
from urllib.parse import quote
import base64, hashlib, secrets, string, time

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(
    no_viewport=True,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
page = ctx.new_page()

client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
scopes = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
params = f"client_id={client_id}&response_type=code&redirect_uri=http://localhost&scope={quote(scopes)}&response_mode=query&prompt=consent&code_challenge={cc}&code_challenge_method=S256"

for name, url in [
    ("consumers", f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?{params}"),
    ("common", f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{params}"),
]:
    print(f"\n=== {name} ===")
    captured = {"code": None}
    page.route("http://localhost/*", lambda r: r.fulfill(body="ok", status=200))
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(4)
        print(f"URL={page.url[:120]}")
        print(f"Title={page.title()}")
        has_email = page.locator('[name="loginfmt"]').count()
        has_pass = page.locator('[name="passwd"]').count()
        print(f"Email={has_email} Pass={has_pass}")
        body = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : 'N/A'")
        print(f"Body: {body[:500]}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)[:100]}")

browser.close()
p.stop()
