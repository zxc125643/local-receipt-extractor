"""Debug the Outlook registration flow step by step with a visible browser"""
from patchright.sync_api import sync_playwright
from backend.app.services.browser.utils import generate_strong_password, random_email
import time

email_user = random_email()
email = f"{email_user}@outlook.com"
password = generate_strong_password()
year = "1990"
month = "5"
day = "15"

print(f"Attempting to register: {email} / {password}")

p = sync_playwright().start()
browser = p.chromium.launch(headless=False, args=["--lang=zh-CN"])
ctx = browser.new_context(no_viewport=True)
page = ctx.new_page()

page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=20000, wait_until="domcontentloaded")
print("[1] Loaded create_account page")

# Wait for "同意并继续" button
try:
    page.get_by_text('同意并继续').wait_for(timeout=30000)
    print("[2] Found '同意并继续' button")
    page.get_by_text('同意并继续').click(timeout=30000)
    print("[3] Clicked agree")
except Exception as e:
    print(f"[FAIL] Agree button: {e}")
    try:
        page.get_by_text('Accept').wait_for(timeout=5000)
        page.get_by_text('Accept').click(timeout=5000)
        print("[3b] Clicked Accept")
    except:
        pass

time.sleep(3)

# Step: Enter email
try:
    email_sel = '[aria-label="新建电子邮件"], [aria-label="New email"], [placeholder*="电子邮件"], [placeholder*="Email"]'
    email_loc = page.locator(email_sel)
    print(f"[4] Email field count: {email_loc.count()}")
    if email_loc.count() > 0:
        email_loc.first.fill(email_user, delay=100, timeout=10000)
        print("[4] Filled email")
    
    # Click Next
    page.locator('[data-testid="primaryButton"]').first.click(timeout=5000)
    print("[5] Clicked primary button after email")
except Exception as e:
    print(f"[FAIL] Email step: {e}")

time.sleep(5)
print(f"  URL={page.url[:100]}")
print(f"  Title={page.title()}")
body = page.evaluate("() => document.body ? document.body.innerText.substring(0, 500) : ''")
print(f"  Body: {body}")

# Check all buttons/inputs
elems = page.evaluate("""() => {
    const input = document.querySelectorAll("input, button, [role=button]");
    return Array.from(input).slice(0, 15).map(x => ({
        tag: x.tagName,
        type: x.type || '',
        name: x.name || '',
        id: x.id || '',
        aria: x.getAttribute('aria-label') || '',
        text: (x.textContent || x.value || '').substring(0, 30),
        visible: x.offsetParent !== null
    }));
}""")
print(f"Elements: {elems}")

time.sleep(30)
browser.close()
p.stop()
