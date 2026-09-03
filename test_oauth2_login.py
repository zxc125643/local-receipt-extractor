"""Debug login flow on login.live.com"""
from patchright.sync_api import sync_playwright
import time

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--lang=zh-CN"])
ctx = browser.new_context(
    no_viewport=True,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
page = ctx.new_page()

page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

# Dump full page state
print(f"URL={page.url[:100]}")
print(f"Title={page.title()}")

# Get the email input
email_input = page.locator('#usernameEntry')
print(f"Email input: count={email_input.count()}")

if email_input.count() > 0:
    # Check what attributes it has
    attrs = page.evaluate("""() => {
        const el = document.querySelector('#usernameEntry');
        if (!el) return null;
        return {
            name: el.name,
            id: el.id,
            type: el.type,
            placeholder: el.placeholder,
            autocomplete: el.autocomplete,
            form: el.form ? el.form.id : null,
            parent_form: el.closest('form') ? el.closest('form').id || 'has-form' : 'no-form'
        };
    }""")
    print(f"Email input attrs: {attrs}")

    # Check form
    forms = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('form')).map(f => ({
            id: f.id,
            action: (f.action || '').substring(0,80),
            method: f.method
        }));
    }""")
    print(f"Forms: {forms}")

    # Try keyboard Enter instead of button click
    print("\nFilling email...")
    email_input.fill("test@outlook.com", timeout=5000)
    time.sleep(1)

    # Press Enter
    print("Pressing Enter...")
    page.keyboard.press("Enter")
    time.sleep(5)

    print(f"URL={page.url[:100]}")
    print(f"Title={page.title()}")
    body = page.evaluate("() => document.body ? document.body.innerText.substring(0,500) : 'N/A'")
    print(f"Body: {body[:500]}")
    pw_count = page.locator('input[type="password"]').count()
    print(f"Password inputs: {pw_count}")

browser.close()
p.stop()
