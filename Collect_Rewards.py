import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True 
# ---------------------

def login_and_save(browser):
    print("Starting fresh login...")
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

        # Accept cookies
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=5000)
        except:
            pass

        print("Clicking LOG IN...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        page.wait_for_timeout(3000) 

        print("Opening Kabam Auth window...")
        with context.expect_page() as new_page_info:
            page.locator("button:has-text('Log In')").last.click()
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        auth_page.keyboard.press("Enter")

        # Wait for redirect back to main store
        page.wait_for_selector("button:has-text('CART')", timeout=45000)
        
        # Save session temporarily for this specific run
        context.storage_state(path=SESSION_FILE)
        print("Login successful.")
    except Exception as e:
        print(f"Login failed: {e}")
        page.screenshot(path="login_error.png")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    
    # Scroll to load all store sections
    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
    page.wait_for_timeout(2000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)
    
    # Take a screenshot of the store state for your records
    page.screenshot(path="store_view.png")
    
    claimed = 0
    # Loop to find and click rewards
    while claimed < 20:
        # Check for both "GET FREE" and "CLAIM" labels
        buttons = page.locator("button:has-text('GET FREE'), button:has-text('CLAIM')")
        
        if buttons.count() == 0:
            print("No claimable rewards found at this time.")
            break

        print(f"Attempting to claim reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            btn.click(force=True)
            
            # Wait for the "Success" popup and close it
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception as e:
            print("Could not click button, refreshing...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(5000)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Error: Secrets KABAM_EMAIL or KABAM_PASSWORD are missing in GitHub Settings.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # Step 1: Login
        login_and_save(browser)

        # Step 2: Use the newly created session to claim
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
            claim_rewards(page)
            # Final success screenshot
            page.screenshot(path="final_status.png")
        except Exception as e:
            print(f"Runtime error: {e}")
            page.screenshot(path="runtime_error.png")
        finally:
            print("Process complete.")
            browser.close()

if __name__ == "__main__":
    run()
