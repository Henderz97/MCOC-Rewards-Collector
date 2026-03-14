import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True 

def login_and_save(browser):
    print("Starting login process...")
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    try:
        print("Navigating to store...")
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)

        # Handle Cookie Banner
        try:
            page.get_by_role("button", name=re.compile("accept|agree|allow|ok", re.I)).click(timeout=5000)
        except:
            pass

        print("Locating Login button...")
        login_btn = page.get_by_role("button", name=re.compile("log in", re.I)).first
        page.wait_for_selector("button:has-text('LOG IN')", state="visible")

        # Trigger the login popup using a JS dispatch to bypass overlay issues
        print("Opening Login Popup...")
        with context.expect_page(timeout=60000) as new_page_info:
            login_btn.dispatch_event("click")
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Filling credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        auth_page.get_by_role("button", name=re.compile("log in", re.I)).click()

        # Wait for redirect back to store and session to settle
        print("Waiting for session redirect...")
        page.wait_for_selector("text=LOG OUT", timeout=90000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
    except Exception as e:
        page.screenshot(path="login_error.png")
        print(f"Login failed: {e}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_timeout(5000)
    
    claimed = 0
    # Try multiple passes as claiming one item often unlocks another
    for pass_num in range(3):
        buttons = page.get_by_role("button", name=re.compile("get free|claim", re.I))
        count = buttons.count()
        
        if count == 0:
            print(f"No rewards found on pass {pass_num + 1}.")
            break

        for i in range(count):
            try:
                btn = buttons.nth(i)
                if btn.is_visible():
                    print(f"Claiming reward {claimed + 1}...")
                    btn.click(force=True)
                    page.wait_for_timeout(4000)
                    page.keyboard.press("Escape") # Close success modal
                    claimed += 1
            except Exception as e:
                print(f"Could not claim item {i}: {e}")
        
        page.reload()
        page.wait_for_timeout(5000)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Error: KABAM_EMAIL or KABAM_PASSWORD not set in Secrets.")
        return

    with sync_playwright() as p:
        # Standard launch
        browser = p.chromium.launch(headless=HEADLESS)
        
        # Determine if we need to log in
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(
            storage_state=SESSION_FILE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Session Check
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible():
                print("Session expired. Re-logging...")
                login_and_save(browser)
                # Refresh page with new credentials
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto("https://store.playcontestofchampions.com/")

            claim_rewards(page)
        except Exception as e:
            print(f"Runtime error: {e}")
            page.screenshot(path="runtime_error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
