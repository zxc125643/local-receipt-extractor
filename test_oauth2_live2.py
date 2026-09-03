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
url = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?{params}"

captured = {"code": None}
page.route("http://localhost/*", lambda r: r.fulfill(body="ok", status=200))
page.goto(url, wait_until="domcontentloaded", timeout=25000)
time.sleep(4)

print(f"URL={page.url[:120]}")
print(f"Title={page.title()}")

# Dump form elements
inputs = page.evaluate("""() => {
    const i = document.querySelectorAll('input, button, a');
    return Array.from(i).slice(0,20).map(x => ({
        tag: x.tagName,
        name: x.name || '',
        id: x.id || '',
        type: x.type || '',
        text: (x.textContent || x.value || x.title || '').substring(0,40),
        placeholder: x.placeholder || '',
        visible: x.offsetParent !== null
    }));
}""")
print("\nForm elements:")
for inp in inputs:
    print(f"  {inp}")

# Also check for the email/phone input by placeholder or aria-label
by_placeholder = page.locator('[placeholder*="Email"], [placeholder*="phone"], [placeholder*="Phone"]').count()
by_aria = page.locator('[aria-label*="Email"], [aria-label*="Phone"]').count()
print(f"\nBy placeholder: {by_placeholder}")
print(f"By aria-label: {by_aria}")

# Check what the input actually is
page_html = page.evaluate("() => document.body.innerHTML.substring(0, 5000)")
print(f"\nHTML snippet:\n{page_html}")

browser.close()
p.stop()
