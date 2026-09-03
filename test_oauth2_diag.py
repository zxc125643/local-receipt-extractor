from patchright.sync_api import sync_playwright
from urllib.parse import quote, urlparse, parse_qs
import base64, hashlib, secrets, string, time, os, json

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
redirect_url = "http://localhost"
scopes = ["offline_access", "https://outlook.office.com/IMAP.AccessAsUser.All"]
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
params = {
    "client_id": client_id, "response_type": "code", "redirect_uri": redirect_url,
    "scope": " ".join(scopes), "response_mode": "query", "prompt": "consent",
    "code_challenge": cc, "code_challenge_method": "S256",
}
url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(f"{k}={quote(v)}" for k,v in params.items())

captured = {"code": None}

def handle_redirect(route):
    u = route.request.url
    print(f"[ROUTE] {u[:150]}")
    if "code=" in u and "?" in u:
        c = parse_qs(u.split("?")[1])
        if "code" in c:
            captured["code"] = c["code"][0]
    route.fulfill(body="ok", status=200)

page.route("http://localhost/*", handle_redirect)
page.goto(url, wait_until="domcontentloaded", timeout=30000)
time.sleep(5)

print(f"\nURL={page.url[:120]}")
print(f"Title={page.title()}")
print(f"Captured={captured['code']}")

sd = "F:/project/nixiang/outlook-batch-manager/screenshots"
os.makedirs(sd, exist_ok=True)
page.screenshot(path=f"{sd}/diag_step0.png")

# Dump page info
raw = page.evaluate("() => JSON.stringify({ bodyLen: document.body.innerText.length, text: document.body.innerText.substring(0,1000), htmlLen: document.documentElement.outerHTML.length })")
info = json.loads(raw)
print(f"Body len: {info['bodyLen']}  HTML len: {info['htmlLen']}")

# Check iframes
fcount = len(page.frames)
print(f"Frames: {fcount}")
if fcount > 1:
    for i, f in enumerate(page.frames):
        try:
            print(f"  [{i}] {f.url[:100]} title={f.title[:50]}")
        except: pass
    # Try searching in child frames for login elements
    for fi, f in enumerate(page.frames):
        try:
            ec = f.locator('[name="loginfmt"]').count()
            pc = f.locator('[name="passwd"]').count()
            if ec > 0 or pc > 0:
                print(f"  Frame {fi} has login form! email={ec} pass={pc}")
        except: pass

print(f"\nFinal: URL={page.url[:120]} Captured={captured['code']}")
print(f"Screenshot: {sd}/diag_step0.png")

browser.close()
p.stop()
