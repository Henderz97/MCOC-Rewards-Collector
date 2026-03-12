import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = "zachhender@walla.co.il"
PASSWORD = "23041997" # Ensure this is correct
SESSION_FILE = "kabam_session.json"
HEADLESS = True  # Set to True to run invisibly in the background or False
# ---------------------

def login_and_save(browser):
    print("Starting login process...")
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

        # Accept cookies if present
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=3000)
        except:
            pass

        # Click LOG IN in the top right
        print("Clicking top-right LOG IN button...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        time.sleep(3) # Wait for animation

        # Trigger and catch the Kabam login popup
        print("Waiting for Kabam login window...")
        with context.expect_page() as new_page_info:
            # We use a broader selector for the orange button to be safe
            page.evaluate("() => document.querySelector('button[class*=\"orange\"], .modal-content button')?.click()")
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        # Fill credentials
        print("Filling credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)

        # Use Enter to submit (Most reliable method found)
        print("Submitting via Enter...")
        auth_page.keyboard.press("Enter")

        # Wait for the main page to show 'CART' as proof of login
        page.wait_for_selector("button:has-text('CART')", timeout=30000)
        
        # Save session for tomorrow
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
    except Exception as e:
        print(f"Login failed: {e}")
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    time.sleep(5) # Allow store items to load
    
    claimed = 0
    # Specifically target 'GET FREE' to avoid 'OWNED' items
    while claimed < 20:
        buttons = page.get_by_role("button", name=re.compile("get free", re.I))
        
        if buttons.count() == 0:
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            
            # Dismiss the success modal
            time.sleep(4)
            page.keyboard.press("Escape")
            time.sleep(2)
            claimed += 1
        except:
            print("Action blocked, refreshing page...")
            page.reload()
            time.sleep(5)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    with sync_playwright() as p:
        # Toggle HEADLESS here for background running
        browser = p.chromium.launch(headless=HEADLESS)

        # Initial login if no session file exists
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Double-check if we are logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible(timeout=5000):
                print("Session expired. Performing fresh login...")
                context.close()
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                login_and_save(browser)
                # Re-open with new session
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