"""Test using login.live.com MSA endpoint directly"""
from patchright.sync_api import sync_playwright
from urllib.parse import quote, parse_qs
import base64, hashlib, secrets, string, time, os, json

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

# Test 1: Try consumers endpoint
client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
scopes = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"

params = f"client_id={client_id}&response_type=code&redirect_uri=http://localhost&scope={quote(scopes)}&response_mode=query&prompt=consent&code_challenge={cc}&code_challenge_method=S256"

# Test A: consumers tenant
url_a = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?{params}"
print(f"=== Test A: consumers endpoint ===")
captured = {"code": None}
page.route("http://localhost/*", lambda r: r.fulfill(body="ok", status=200))
page.goto(url_a, wait_until="networkidle", timeout=45000)
time.sleep(3)
print(f"URL={page.url[:120]}")
print(f"Title={page.title()}")

# Check for login form
has_email = page.locator('[name="loginfmt"]').count()
has_pass = page.locator('[name="passwd"]').count()
has_consent = page.locator('[data-testid="appConsentPrimaryButton"]').count()
print(f"Email={has_email} Pass={has_pass} Consent={has_consent}")

body = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : 'N/A'")
print(f"Body: {body[:500]}")

# Test B: Try the urlMsaSignUp approach
url_b = f"https://login.live.com/oauth20_authorize.srf?{params}"
print(f"\n=== Test B: login.live.com MSA endpoint ===")
page2 = ctx.new_page()
captured2 = {"code": None}
page2.route("http://localhost/*", lambda r: r.fulfill(body="ok", status=200))
page2.goto(url_b, wait_until="networkidle", timeout=45000)
time.sleep(3)
print(f"URL={page2.url[:120]}")
print(f"Title={page2.title()}")

has_email2 = page2.locator('[name="loginfmt"]').count()
has_pass2 = page2.locator('[name="passwd"]').count()
has_consent2 = page2.locator('[data-testid="appConsentPrimaryButton"]').count()
print(f"Email={has_email2} Pass={has_pass2} Consent={has_consent2}")

body2 = page2.evaluate("() => document.body ? document.body.innerText.substring(0,500) : 'N/A'")
print(f"Body: {body2[:500]}")

# Check for login form in url_b
if has_email2 > 0:
    print("\nFound login form on login.live.com!")
    page2.locator('[name="loginfmt"]').first.fill("testuser@outlook.com", timeout=5000)
    page2.locator('#idSIButton9').click(timeout=5000)
    time.sleep(3)
    print(f"After email: URL={page2.url[:120]} Title={page2.title()}")
    if page2.locator('[name="passwd"]').count() > 0:
        print("Password form shown!")
    elif page2.locator('[data-testid="appConsentPrimaryButton"]').count() > 0:
        print("Consent page shown!")
        page2.locator('[data-testid="appConsentPrimaryButton"]').click(timeout=5000)
        time.sleep(3)
        print(f"After consent: URL={page2.url[:120]}")

sd = "F:/project/nixiang/outlook-batch-manager/screenshots"
os.makedirs(sd, exist_ok=True)
page.screenshot(path=f"{sd}/diag3_a.png")
page2.screenshot(path=f"{sd}/diag3_b.png")
print(f"\nScreenshots saved")

browser.close()
p.stop()
