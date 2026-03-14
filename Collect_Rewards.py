import os
import time
from playwright.sync_api import sync_playwright, TimeoutError

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL") or "your_email_here"
PASSWORD = os.getenv("PASSWORD") or "your_password_here"
SESSION_FILE = "kabam_session.json"
HEADLESS = True
# ---------------------

def login_and_save(browser):
    page = browser.new_page()
    print("Starting login process...")

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="domcontentloaded", timeout=60000)

        # Try clicking the login button
        page.locator("text=Log in").first.click()
        time.sleep(1)

        popup = None
        try:
            # Wait briefly to see if a popup opens
            popup = page.wait_for_event("popup", timeout=5000)
            print("Popup detected.")
        except TimeoutError:
            print("No popup opened, using main page for login.")

        login_page = popup if popup else page

        # Fill in credentials
        login_page.fill('input[type="email"]', EMAIL)
        login_page.fill('input[type="password"]', PASSWORD)
        login_page.click('button:has-text("Login")')
        time.sleep(2)

        # Optional "Stay logged in?" dialog
        try:
            login_page.locator('button:has-text("Yes")').click(timeout=2000)
        except:
            pass

        # Save session
        context = login_page.context
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")

        if popup:
            popup.close()
        page.close()
    except TimeoutError:
        print("Login failed: Timeout while loading page or login fields.")
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

        # Example: collect rewards placeholder
        print("Scanning for rewards...")
        # Example reward collection:
        # for btn in page.locator("button:has-text('Collect')").all():
        #     btn.click()
        #     time.sleep(0.5)

        print("Reward collection complete.")
        browser.close()

if __name__ == "__main__":
    run()
