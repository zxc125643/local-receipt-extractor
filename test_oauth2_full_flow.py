from patchright.sync_api import sync_playwright
from urllib.parse import quote, parse_qs
import base64, hashlib, secrets, string, time
import sys; sys.path.insert(0, '.')
from backend.app.db.database import SessionLocal
from backend.app.db.models import Account
from sqlalchemy import select

s = SessionLocal()
a = s.execute(select(Account).order_by(Account.created_at.desc())).scalars().first()
email_user = a.email.replace("@outlook.com", "")
password = a.password
print(f"Account: {a.email}")
s.close()

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(
    no_viewport=True,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
page = ctx.new_page()

captured = {"code": None}

def handle_redirect(route):
    u = route.request.url
    if "code=" in u and "?" in u:
        c = parse_qs(u.split("?")[1])
        if "code" in c:
            captured["code"] = c["code"][0]
    route.fulfill(body="ok", status=200)

page.route("http://localhost/*", handle_redirect)

# Step 1: Login
print("=== Login ===")
page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

if page.locator('#usernameEntry').count() > 0:
    page.locator('#usernameEntry').fill(email_user, timeout=8000)
    time.sleep(1)
    page.keyboard.press("Enter")
    time.sleep(4)

    # Password entry page
    pw_input = page.locator('input[type="password"]')
    if pw_input.count() > 0:
        # Check attrs
        attrs = page.evaluate("""() => {
            const el = document.querySelector('input[type="password"]');
            return el ? {id: el.id, name: el.name, autocomplete: el.autocomplete} : null;
        }""")
        print(f"Password input: {attrs}")
        
        pw_input.first.fill(password, timeout=8000)
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(5)

    # Handle "Stay signed in?"
    try:
        for sel in ['#declineButton', 'input[value="No"]', 'button:has-text("No")']:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=5000)
                time.sleep(2)
    except: pass

print(f"After login: URL={page.url[:120]} Title={page.title()}")

# Step 2: OAuth2
print("\n=== OAuth2 ===")
client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
scopes = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
params = f"client_id={client_id}&response_type=code&redirect_uri=http://localhost&scope={quote(scopes)}&response_mode=query&prompt=consent&code_challenge={cc}&code_challenge_method=S256"
url = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?{params}"

captured["code"] = None
page.goto(url, wait_until="domcontentloaded", timeout=30000)
time.sleep(5)

print(f"After: URL={page.url[:120]} Title={page.title()} Code={captured['code']}")

body = page.evaluate("() => document.body ? document.body.innerText.substring(0,800) : 'N/A'")
print(f"Body: {body[:500]}")

if not captured["code"]:
    btns = page.evaluate("""() => {
        const b = document.querySelectorAll("button");
        return Array.from(b).map(x => ({
            text: (x.textContent || "").substring(0,50),
            id: x.id, visible: x.offsetParent !== null
        }));
    }""")
    print(f"Buttons: {btns}")

    for sel in ['[data-testid="appConsentPrimaryButton"]', 'input[value="Yes"]',
                 'input[value="Accept"]', 'button:has-text("Yes")',
                 'button:has-text("Accept")']:
        c = page.locator(sel)
        if c.count() > 0:
            print(f"Click: {sel}")
            c.first.click(timeout=8000)
            time.sleep(4)
            print(f"  URL={page.url[:120]} Code={captured['code']}")

time.sleep(3)
print(f"\nFinal: URL={page.url[:120]} Code={captured['code']}")

if captured["code"]:
    import requests
    r = requests.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        data={"client_id": client_id, "code": captured["code"],
              "redirect_uri": "http://localhost", "grant_type": "authorization_code",
              "code_verifier": cv, "scope": scopes},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    print(f"\nToken: {r.status_code}")
    if r.ok:
        j = r.json()
        print(f"  RT: {'refresh_token' in j}")
        if "refresh_token" in j:
            print(f"  RT={j['refresh_token'][:50]}...")

browser.close()
p.stop()
