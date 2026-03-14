from playwright.sync_api import sync_playwright, TimeoutError
import os, time

EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True

def login_and_save(browser):
    page = browser.new_page()
    print("Starting login process...")
    page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)

    # Click the main "Log in" button
    page.locator("text=Log in").first.click()
    time.sleep(1)

    # Wait for popup to appear
    try:
        popup = page.wait_for_event("popup", timeout=10000)
        login_page = popup
        print("Popup detected for login.")
    except TimeoutError:
        # Sometimes no popup; check if iframe appears
        login_page = page
        iframe = None
        for f in page.frames:
            if "accounts.kabam.com" in f.url:
                iframe = f
                break
        if iframe:
            login_page = iframe
            print("Login iframe detected.")
        else:
            print("No popup or iframe detected. Login will likely fail.")
    
    try:
        # Wait for email input in the detected page or iframe
        login_page.wait_for_selector('input[name="email"], input[type="email"]', timeout=20000)
        login_page.fill('input[name="email"], input[type="email"]', EMAIL)
        login_page.fill('input[name="password"]', PASSWORD)
        login_page.click('button:has-text("Login")')
        time.sleep(2)
        login_page.context.storage_state(path=SESSION_FILE)
        print("Login successful, session saved.")
    except TimeoutError:
        print("Email/password fields did not load. Cannot login.")
        raise

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        login_and_save(browser)
        browser.close()

if __name__ == "__main__":
    run()
