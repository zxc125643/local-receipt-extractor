from patchright.sync_api import sync_playwright
import time
import sys; sys.path.insert(0, '.')
from backend.app.db.database import SessionLocal
from backend.app.db.models import Account
from sqlalchemy import select

s = SessionLocal()
# Try account #1 (the first one, registered via direct connection)
a = s.execute(select(Account).where(Account.id == 1)).scalars().first()
email = a.email.replace("@outlook.com", "")
password = a.password
print(f"Testing: {a.email} / {password}")
s.close()

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)

for attempt in range(3):
    page = ctx.new_page()
    page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    
    if page.locator("#usernameEntry").count() == 0:
        print(f"Attempt {attempt+1}: Already logged in!")
        break
    
    page.locator("#usernameEntry").fill(email, timeout=5000)
    time.sleep(1)
    page.keyboard.press("Enter")
    time.sleep(5)
    
    body = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : ''")
    
    if "couldn't find" in body.lower() or "doesn't exist" in body.lower():
        print(f"Attempt {attempt+1}: Account '{a.email}' DOES NOT EXIST!")
        break
    
    if page.locator("input[type=password]").count() > 0:
        print(f"Attempt {attempt+1}: Account exists! Found password page.")
        page.locator("input[type=password]").fill(password, timeout=5000)
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(5)
        
        body2 = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : ''")
        if "Enter your password" not in body2 or page.url != "https://login.live.com/":
            print(f"After password: {page.url[:100]} Title={page.title()}")
            print(f"Body: {body2}")
        break
    
    # Try again with a new page
    page.close()

browser.close()
p.stop()
