from patchright.sync_api import sync_playwright
from urllib.parse import quote, parse_qs
import base64, hashlib, secrets, string, time, os

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

client_id = "ca3ea24d-3090-4b66-889a-a0d991d505af"
cv = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
params = {
    "client_id": client_id, "response_type": "code", "redirect_uri": "http://localhost",
    "scope": "offline_access https://outlook.office.com/IMAP.AccessAsUser.All",
    "response_mode": "query", "prompt": "consent",
    "code_challenge": cc, "code_challenge_method": "S256",
}
url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(f"{k}={quote(v)}" for k,v in params.items())

page.route("http://localhost/*", lambda r: r.fulfill(body="ok", status=200))

# Try networkidle for full JS render
page.goto(url, wait_until="networkidle", timeout=45000)
time.sleep(3)

print(f"URL={page.url[:120]}")
print(f"Title={page.title()}")

# Check where the content is
head_html = page.evaluate("() => document.head.innerHTML.substring(0, 2000)")
print(f"\nHEAD (first 2000):\n{head_html}")

# Check if there's a redirect meta tag or script
meta_redirect = page.evaluate("""() => {
    const metas = document.querySelectorAll('meta');
    return Array.from(metas).map(m => ({ httpEquiv: m.httpEquiv, content: m.content, name: m.name }));
}""")
print(f"\nMeta tags: {meta_redirect}")

# Check for script redirects
scripts = page.evaluate("""() => {
    const s = document.querySelectorAll('script');
    return Array.from(s).slice(0,5).map(x => ({ src: x.src.substring(0,80), text: (x.textContent || '').substring(0,100) }));
}""")
print(f"Scripts: {scripts}")

# Check what's in body
body_html = page.evaluate("() => document.body ? document.body.innerHTML.substring(0, 3000) : 'NO BODY'")
print(f"\nBODY HTML (first 3000):\n{body_html}")

# Check if there's a shadow root or special div
divs = page.evaluate("""() => {
    const d = document.querySelectorAll('div');
    return Array.from(d).slice(0,10).map(x => ({ id: x.id, cls: (x.className || '').substring(0,30), visible: x.offsetParent !== null }));
}""")
print(f"\nDivs: {divs}")

# Check all root elements
root_elements = page.evaluate("""() => {
    return Array.from(document.body ? document.body.children : []).slice(0,10).map(x => ({
        tag: x.tagName, id: x.id, cls: (x.className || '').substring(0,30)
    }));
}""")
print(f"Root children: {root_elements}")

sd = "F:/project/nixiang/outlook-batch-manager/screenshots"
os.makedirs(sd, exist_ok=True)
page.screenshot(path=f"{sd}/diag2.png")
print(f"\nScreenshot saved")

browser.close()
p.stop()
