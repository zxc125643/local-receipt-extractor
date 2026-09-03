from patchright.sync_api import sync_playwright
from urllib.parse import quote, urlparse, parse_qs
import base64, hashlib, secrets, string, time

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

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

captured = {"code": None}

def handle_redirect(route):
    req_url = route.request.url
    if "code=" in req_url:
        qs = parse_qs(urlparse(req_url).query)
        if "code" in qs:
            captured["code"] = qs["code"][0]
    route.fulfill(body="ok", status=200)

page.route("http://localhost/*", handle_redirect)
page.goto(url, wait_until="domcontentloaded", timeout=30000)
time.sleep(3)
print("After goto:", page.url[:150])

try:
    title = page.title()
    print("Title:", title)
except:
    pass

body = page.evaluate("() => document.body.innerText.substring(0, 500)")
print("Body:", body[:500])

btns = page.evaluate("""() => {
    const b = document.querySelectorAll("button, input[type=submit]");
    return Array.from(b).slice(0,10).map(x => ({
        text: (x.textContent || x.value || "").substring(0,30),
        id: x.id || ""
    }));
}""")
print("Buttons:", btns)
print("Captured code:", captured["code"])
print("Final URL:", page.url[:150])

time.sleep(3)
print("Captured code after wait:", captured["code"])
print("Final URL after wait:", page.url[:150])

browser.close()
p.stop()
