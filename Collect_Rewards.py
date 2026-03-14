import os
import time
from playwright.sync_api import sync_playwright, TimeoutError

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL") or "zachhender@walla.co.il"
PASSWORD = os.getenv("PASSWORD") or "23041997"
SESSION_FILE = "kabam_session.json"
HEADLESS = True
# ---------------------

def login_and_save(browser):
    page = browser.new_page()
    print("Starting login process...")

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)

        # Click main login button
        page.locator("text=Log in").first.click()
        time.sleep(1)

        popup = None
        try:
            # Check if a popup opens
            popup = page.wait_for_event("popup", timeout=5000)
            print("Popup detected.")
        except TimeoutError:
            print("No popup opened, using main page for login.")

        login_page = popup if popup else page

        # Wait for email input (main page or iframe)
        try:
            # Handle iframe login if present
            frame = None
            iframes = login_page.frames
            for f in iframes:
                if f.url.startswith("https://accounts.kabam.com"):  # login iframe URL
                    frame = f
                    break

            target = frame or login_page
            target.wait_for_selector('input[type="email"]', timeout=20000)
            target.fill('input[type="email"]', EMAIL)
            target.fill('input[type="password"]', PASSWORD)
            target.click('button:has-text("Login")')
            time.sleep(2)

            # Optional: handle "Stay logged in?" dialog
            try:
                target.locator('button:has-text("Yes")').click(timeout=2000)
            except:
                pass

            # Save session
            login_page.context.storage_state(path=SESSION_FILE)
            print("Login successful. Session saved.")

        except TimeoutError:
            print("Email/password fields did not load in time.")
            raise

        if popup:
            popup.close()
        page.close()

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
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)
        except TimeoutError:
            print("Main page load timed out, proceeding anyway.")

        # Example: collect rewards
        print("Scanning for rewards...")
        # Example reward collection:
        # for btn in page.locator("button:has-text('Collect')").all():
        #     btn.click()
        #     time.sleep(0.5)

        print("Reward collection complete.")
        browser.close()

if __name__ == "__main__":
    run()
