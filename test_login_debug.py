from patchright.sync_api import sync_playwright
import time
import sys; sys.path.insert(0, '.')
from backend.app.db.database import SessionLocal
from backend.app.db.models import Account
from sqlalchemy import select

s = SessionLocal()
a = s.execute(select(Account).order_by(Account.created_at.desc())).scalars().first()
email = a.email.replace("@outlook.com", "")
password = a.password
print(f"Testing: {a.email} / {password}")
s.close()

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

# Step 1: enter email
print("Filling email...")
page.locator("#usernameEntry").fill(email, timeout=5000)
time.sleep(1)
page.keyboard.press("Enter")
time.sleep(5)

print(f"URL={page.url[:100]}")
print(f"Title={page.title()}")
body = page.evaluate("() => document.body ? document.body.innerText.substring(0,1000) : ''")
print(f"Body: {body}")
pw_count = page.locator("input[type=password]").count()
print(f"Password fields: {pw_count}")

if pw_count > 0:
    page.locator("input[type=password]").fill(password, timeout=5000)
    time.sleep(1)
    page.keyboard.press("Enter")
    time.sleep(5)
    print(f"\nAfter password: URL={page.url[:100]} Title={page.title()}")
    body2 = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : ''")
    print(f"Body: {body2}")

browser.close()
p.stop()
