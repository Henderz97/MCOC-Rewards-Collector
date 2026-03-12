import os
import time
import re
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
# We pull these from GitHub Secrets for security
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True  # Must be True for GitHub Actions

def login_and_save(browser):
    print("Initiating login sequence...")
    # Add a real User-Agent to help bypass bot detection
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    
    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)
        
        # 1. Clear Cookies
        try:
            page.get_by_role("button", name=re.compile(r"ACCEPT ALL", re.IGNORECASE)).click(timeout=5000)
        except: pass

        # 2. Click Login
        print("Clicking top-right LOG IN button...")
        page.locator("header button").filter(has_text=re.compile(r"LOG IN", re.IGNORECASE)).click()
        
        # 3. Handle Modal/Popup
        time.sleep(5)
        auth_tab = None
        for i in range(10):
            if len(context.pages) > 1:
                auth_tab = context.pages[1]
                break
            # Try to force the orange button to click if the popup didn't open
            page.evaluate("() => document.querySelector('button[class*=\"orange\"], .modal-content button')?.click()")
            time.sleep(2)

        if not auth_tab: 
            print("Auth tab (popup) never opened.")
            # Take a screenshot to debug why
            page.screenshot(path="error_screenshot.png")
            return False

        # 4. Fill Credentials
        print("Auth tab detected! Entering credentials...")
        auth_tab.wait_for_selector('input[type="email"]', timeout=20000)
        auth_tab.fill('input[type="email"]', EMAIL)
        auth_tab.fill('input[type="password"]', PASSWORD)
        
        # 5. Submission
        print("Submitting via 'Enter' key press...")
        auth_tab.focus('input[type="password"]')
        auth_tab.keyboard.press("Enter")
        
        # 6. Monitor for Success
        print("Monitoring for successful login...")
        success = False
        for _ in range(45):
            # Check if main page now shows 'CART'
            if page.locator("header button").filter(has_text=re.compile(r"CART", re.IGNORECASE)).is_visible():
                if not page.locator("header button").filter(has_text=re.compile(r"LOG IN", re.IGNORECASE)).is_visible():
                    print("Login confirmed by main page!")
                    success = True
                    break
            
            if auth_tab.is_closed():
                success = True
                break
            time.sleep(1)

        if not success:
            print("Login failed or timed out.")
            page.screenshot(path="error_screenshot.png")
            return False
        
        time.sleep(5) 
        context.storage_state(path=SESSION_FILE)
        print("Session saved successfully.")
        return True

    except Exception as e:
        print(f"Error during login: {e}")
        page.screenshot(path="error_screenshot.png")
        return False
    finally:
        context.close()

def claim_rewards(page):
    print("Claiming rewards...")
    time.sleep(10) # Give the store time to load items
    claimed = 0
    while True:
        # Looking for 'GET FREE'
        btn = page.locator("button, a").filter(has_text=re.compile(r"Get free|Claim", re.IGNORECASE)).first
        
        if not btn.is_visible() or claimed >= 20:
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            time.sleep(6)
            page.keyboard.press("Escape") 
            time.sleep(3)
            claimed += 1
        except:
            print("Button click failed, reloading...")
            page.reload()
            time.sleep(8)
            
    print(f"Done! Total: {claimed}")

def run():
    with sync_playwright() as p:
        # Added args to help bypass data-center detection
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        # Always try to login fresh in GitHub Actions unless you have a persistent session
        if not login_and_save(browser):
            print("Could not establish session.")
            browser.close()
            return

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
            claim_rewards(page)
        except Exception as e:
            print(f"Error during claiming: {e}")
        finally:
            browser.close()
            print("Process complete.")

if __name__ == "__main__":
    run()
