from patchright.sync_api import sync_playwright
from urllib.parse import quote, urlparse, parse_qs
import base64, hashlib, secrets, string, time
import sys; sys.path.insert(0, '.')
from backend.app.db.database import SessionLocal
from backend.app.db.models import Account
from sqlalchemy import select
from backend.app.services.secret_store import PlaintextSecretStore

s = SessionLocal()
a = s.execute(select(Account).order_by(Account.created_at.desc())).scalars().first()
if not a:
    print("No accounts")
    exit(1)
pw = a.password
email_user = a.email.replace("@outlook.com", "")
print(f"Account: {a.email} / {pw}")
s.close()

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

# Step 1: Login at login.live.com
print("\n=== Login ===")
page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

if "outlook" in page.url.lower() or not page.locator('[name="loginfmt"]').count():
    print("Already logged in!")
else:
    page.locator('[name="loginfmt"]').fill(email_user, timeout=10000)
    page.locator('#idSIButton9').click(timeout=10000)
    time.sleep(3)
    page.locator('[name="passwd"]').fill(pw, timeout=10000)
    page.locator('#idSIButton9').click(timeout=10000)
    time.sleep(5)
    try:
        if page.locator('[name="DontShowAgain"]').count() > 0:
            page.locator('[name="DontShowAgain"]').click(timeout=5000)
            page.locator('#idSIButton9').click(timeout=10000)
    except: pass
    try:
        if page.locator('#declineButton').count() > 0:
            page.locator('#declineButton').click(timeout=5000)
    except: pass
    time.sleep(3)

print(f"After login: {page.url[:100]}")

# Step 2: OAuth2 authorize
print("\n=== OAuth2 ===")
client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
redirect_url = "http://localhost"
scopes = ["offline_access", "https://outlook.office.com/IMAP.AccessAsUser.All"]
alphabet = string.ascii_letters + string.digits + "-._~"
cv = "".join(secrets.choice(alphabet) for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
params = {
    "client_id": client_id, "response_type": "code", "redirect_uri": redirect_url,
    "scope": " ".join(scopes), "response_mode": "query", "prompt": "consent",
    "code_challenge": cc, "code_challenge_method": "S256",
}
url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(f"{k}={quote(v)}" for k,v in params.items())

captured = {"code": None}
def handle_redirect(route):
    req_url = route.request.url
    print(f"  Route: {req_url[:130]}")
    if "code=" in req_url:
        qs = parse_qs(urlparse(req_url).query)
        if "code" in qs:
            captured["code"] = qs["code"][0]
            print(f"  CODE: {captured['code'][:30]}...")
    route.fulfill(body="ok", status=200)
page.route("http://localhost/*", handle_redirect)

page.goto(url, wait_until="domcontentloaded", timeout=30000)
time.sleep(5)
print(f"After authorize: {page.url[:120]}")
print(f"Title: {page.title()}")

body = page.evaluate("() => document.body.innerText.substring(0, 1500)")
print(f"Body[:1500]: {body}")

btns = page.evaluate("""() => {
    const b = document.querySelectorAll("button,input[type=submit]");
    return Array.from(b).slice(0,12).map(x => ({
        t: (x.textContent || x.value || "").substring(0,40),
        v: x.offsetParent !== null
    }));
}""")
print("Buttons:", btns)

# Try clicking consent
if not captured["code"]:
    for sel in ['#idSIButton9', '[data-testid="appConsentPrimaryButton"]',
                 'input[value="Accept"]', 'input[value="接受"]']:
        try:
            if page.locator(sel).count() > 0:
                print(f"Click {sel}")
                page.locator(sel).first.click(timeout=5000)
                time.sleep(4)
                print(f"  URL: {page.url[:120]}  Code: {captured['code']}")
        except: pass

    # Generic button search
    all_btns = page.evaluate("""() => {
        const b = document.querySelectorAll("button,input[type=submit]");
        return Array.from(b).map(x => ({
            text: (x.textContent || x.value || "").substring(0,60),
            id: x.id || "", cls: (x.className || "").substring(0,30),
            visible: x.offsetParent !== null
        }));
    }""")
    print("All buttons:", all_btns)

time.sleep(3)
print(f"\nFinal: URL={page.url[:120]} Code={captured['code']}")

browser.close()
p.stop()
