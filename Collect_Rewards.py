import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION (Now using Environment Variables for Security) ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True  # Must be True for GitHub Actions
# --------------------------------------------------------------------

def login_and_save(browser):
    print("Starting login process...")
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

        # Accept cookies if present
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=5000)
        except:
            pass

        # Click LOG IN in the top right
        print("Clicking top-right LOG IN button...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        time.sleep(3) 

        # Trigger and catch the Kabam login popup
        print("Waiting for Kabam login window...")
        with context.expect_page() as new_page_info:
            # More robust selector for the login trigger
            page.locator("button:has-text('Log In')").last.click()
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        # Fill credentials
        print("Filling credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)

        # Submit
        print("Submitting...")
        auth_page.keyboard.press("Enter")

        # Wait for redirect back and check for login success (Cart or Logout button)
        page.wait_for_selector("button:has-text('CART')", timeout=45000)
        
        # Save session
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
    except Exception as e:
        print(f"Login failed: {e}")
        raise e # Re-raise to stop the script if login fails
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_timeout(5000) # Give items time to render
    
    claimed = 0
    # Search for "GET" or "FREE" buttons
    while claimed < 20:
        # Looking for the 'FREE' buttons specifically in the store grid
        buttons = page.get_by_role("button", name=re.compile("get free|claim", re.I))
        
        if buttons.count() == 0:
            print("No more free rewards found.")
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            
            # Wait for success modal and dismiss
            page.wait_for_timeout(4000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception as e:
            print(f"Error claiming item: {e}. Refreshing...")
            page.reload()
            page.wait_for_timeout(5000)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Error: KABAM_EMAIL or KABAM_PASSWORD not set in environment.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        # In GitHub Actions, we usually login fresh every time 
        # unless you use Artifacts to store the JSON file.
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Verify if still logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible():
                print("Session expired or invalid. Re-logging...")
                login_and_save(browser)
                # Refresh page with new session
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto("https://store.playcontestofchampions.com/")

            claim_rewards(page)
        except Exception as e:
            print(f"Runtime error: {e}")
        finally:
            print("Process complete.")
            browser.close()

if __name__ == "__main__":
    run()
