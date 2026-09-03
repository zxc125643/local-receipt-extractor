"""
Test OAuth2 PKCE flow with a REAL, working Outlook account.
Uses the consumers tenant -> redirects to login.live.com for MSA auth.
Uses keyboard Enter (not button click) to submit React forms.
"""
from patchright.sync_api import sync_playwright
from urllib.parse import quote, urlparse, parse_qs
import base64, hashlib, secrets, string, time, sys
import requests

# === CONFIG: Edit these with your real working Outlook account ===
EMAIL = "your_email@outlook.com"    # <-- YOUR REAL OUTLOOK EMAIL
PASSWORD = "your_password"          # <-- YOUR REAL OUTLOOK PASSWORD
# ================================================================

if EMAIL == "your_email@outlook.com":
    print("ERROR: Please edit this file with your real Outlook email and password.")
    print("       Or pass them as command-line args: python test_oauth2_real_account.py email@outlook.com password")
    if len(sys.argv) >= 3:
        EMAIL = sys.argv[1]
        PASSWORD = sys.argv[2]
    else:
        sys.exit(1)

EMAIL_USER = EMAIL.replace("@outlook.com", "")
print(f"Using account: {EMAIL}")

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

# Generate PKCE
client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
scopes = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"

# Route interceptor for http://localhost redirect
captured = {"code": None}
def handle_redirect(route):
    u = route.request.url
    print(f"  [ROUTE] {u[:150]}")
    if "code=" in u and "?" in u:
        c = parse_qs(u.split("?")[1])
        if "code" in c:
            captured["code"] = c["code"][0]
            print(f"  [ROUTE] CAPTURED CODE!")
    route.fulfill(body="ok", status=200)

page.route("http://localhost/*", handle_redirect)

# ===== Step 1: Login to Microsoft account =====
print("\n=== Step 1: Login to live.com ===")
page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

if page.locator("#usernameEntry").count() == 0:
    print("Already logged in! Checking if we need to re-login...")
    body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
    print(f"Page says: {body_text[:100]}")
else:
    print("Filling email...")
    page.locator("#usernameEntry").fill(EMAIL_USER, timeout=8000)
    time.sleep(1)
    page.keyboard.press("Enter")
    time.sleep(5)

    if "couldn't find" in (page.evaluate("() => document.body ? document.body.innerText : ''") or "").lower():
        print(f"ERROR: Account '{EMAIL}' does not exist on Microsoft!")
        browser.close()
        p.stop()
        sys.exit(1)

    pw_input = page.locator("input[type=password]")
    if pw_input.count() > 0:
        print("Filling password...")
        pw_input.first.fill(PASSWORD, timeout=8000)
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(5)

        # Handle "Stay signed in?"
        try:
            for sel in ['#declineButton', 'input[value="No"]', 'button:has-text("No")',
                         'button:has-text("Don\'t show")']:
                if page.locator(sel).count() > 0:
                    page.locator(sel).first.click(timeout=5000)
                    time.sleep(2)
                    break
        except: pass

print(f"Login result: URL={page.url[:120]} Title={page.title()}")

# ===== Step 2: OAuth2 authorize via consumers tenant =====
print("\n=== Step 2: OAuth2 Authorize ===")
params = {
    "client_id": client_id, "response_type": "code", "redirect_uri": "http://localhost",
    "scope": scopes, "response_mode": "query", "prompt": "consent",
    "code_challenge": cc, "code_challenge_method": "S256",
}
url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?" + "&".join(f"{k}={quote(v)}" for k,v in params.items())
print(f"Authorize URL (first 200): {url[:200]}")

captured["code"] = None
page.goto(url, wait_until="domcontentloaded", timeout=30000)
time.sleep(5)

print(f"After authorize: URL={page.url[:120]}")
print(f"Title={page.title()}")
print(f"Code={captured['code']}")

# Check page content
body = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1000) : ''")
print(f"Body: {body[:500]}")

if not captured["code"]:
    # Check if login form appeared
    if page.locator("#usernameEntry").count() > 0:
        print("Login form shown again. Entering credentials...")
        page.locator("#usernameEntry").fill(EMAIL_USER, timeout=8000)
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(4)
        
        pw_input = page.locator("input[type=password]")
        if pw_input.count() > 0:
            pw_input.first.fill(PASSWORD, timeout=8000)
            time.sleep(1)
            page.keyboard.press("Enter")
            time.sleep(5)
        
        print(f"After re-login: URL={page.url[:120]} Code={captured['code']}")

    # Look for consent button
    if not captured["code"]:
        btns = page.evaluate("""() => {
            const b = document.querySelectorAll("button");
            return Array.from(b).map(x => ({
                text: (x.textContent || "").substring(0, 50),
                id: x.id, visible: x.offsetParent !== null
            }));
        }""")
        print(f"Buttons: {btns}")
        
        for sel in ['[data-testid="appConsentPrimaryButton"]', 'input[value="Yes"]',
                     'input[value="Accept"]', 'button:has-text("Yes")',
                     'button:has-text("Accept")', 'button:has-text("接受")',
                     '[data-testid="consentAcceptButton"]']:
            c = page.locator(sel)
            if c.count() > 0:
                print(f"Clicking consent: {sel}")
                c.first.click(timeout=8000)
                time.sleep(5)
                print(f"After: URL={page.url[:120]} Code={captured['code']}")
                break

time.sleep(3)
print(f"\n=== RESULT ===")
print(f"Final URL: {page.url[:200]}")
print(f"Auth code captured: {captured['code'] is not None}")

if captured["code"]:
    print(f"\n=== Step 3: Exchange code for tokens ===")
    token_data = {
        "client_id": client_id, "code": captured["code"],
        "redirect_uri": "http://localhost", "grant_type": "authorization_code",
        "code_verifier": cv, "scope": scopes,
    }
    r = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    print(f"Token exchange HTTP {r.status_code}")
    if r.ok:
        j = r.json()
        print(f"Response keys: {list(j.keys())}")
        if "refresh_token" in j:
            print(f"\n*** REFRESH_TOKEN CAPTURED! ***")
            print(f"refresh_token: {j['refresh_token'][:80]}...")
            print(f"access_token: {j.get('access_token', 'N/A')[:80]}...")
            print(f"expires_in: {j.get('expires_in')}")
        else:
            print(f"No refresh_token in response!")
            print(f"Full response: {j}")
    else:
        print(f"Error: {r.text[:300]}")
else:
    print("\nNo auth code captured. OAuth2 flow failed.")
    print("Possible issues:")
    print("  1. login.live.com did not redirect properly")
    print("  2. Consent page not handled correctly")
    print("  3. Route interceptor didn't catch the redirect")
    print(f"  Page URL: {page.url[:150]}")

browser.close()
p.stop()
