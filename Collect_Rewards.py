import os
import time
from playwright.sync_api import sync_playwright, TimeoutError

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL") or "your_email_here"
PASSWORD = os.getenv("PASSWORD") or "your_password_here"
SESSION_FILE = "kabam_session.json"
HEADLESS = True  # Set False if you want to see browser
# ---------------------

def login_and_save(browser):
    page = browser.new_page()
    try:
        print("Starting login process...")
        # Use domcontentloaded to avoid networkidle timeout
        page.goto("https://store.playcontestofchampions.com/", wait_until="domcontentloaded", timeout=60000)

        # Click the initial login button
        page.locator("text=Log in").first.click()
        time.sleep(1)

        # Wait for Kabam login popup
        popup = page.wait_for_event("popup", timeout=10000)
        print("Kabam login popup detected...")

        # Fill credentials in popup
        popup.fill('input[type="email"]', EMAIL)
        popup.fill('input[type="password"]', PASSWORD)
        popup.click('button:has-text("Login")')
        time.sleep(2)

        # Optional: handle "Stay logged in?" or other dialogs
        try:
            popup.locator('button:has-text("Yes")').click(timeout=2000)
        except:
            pass

        # Save session cookies
        context = popup.context
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")

        popup.close()
        page.close()
    except TimeoutError:
        print("Login failed: Timeout while loading page or popup.")
        raise
    except Exception as e:
        print(f"Login failed: {e}")
        raise

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()

        # Load previous session if exists
        if os.path.exists(SESSION_FILE):
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()
            print("Session loaded from file.")
        else:
            page = context.new_page()
            login_and_save(browser)

        # Go to main store page
        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="domcontentloaded", timeout=60000)
        except TimeoutError:
            print("Main page load timed out, proceeding anyway.")

        # Example: collect rewards logic placeholder
        print("Scanning for rewards...")
        # Here you would add the code to find reward buttons and click them
        # For example:
        # for btn in page.locator("button:has-text('Collect')").all():
        #     btn.click()
        #     time.sleep(0.5)

        print("Reward collection complete.")
        browser.close()

if __name__ == "__main__":
    run()
