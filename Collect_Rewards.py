import os
import time
import re
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True 

def login_and_save(browser):
    print("Initiating login sequence...")
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    
    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)
        
        # 1. Clear Overlays
        try:
            page.get_by_role("button", name=re.compile(r"ACCEPT ALL", re.IGNORECASE)).click(timeout=5000)
        except: pass

        # 2. Open Modal
        print("Clicking top-right LOG IN button...")
        page.locator("header button").filter(has_text=re.compile(r"LOG IN", re.IGNORECASE)).click()
        
        # 3. Trigger Kabam Popup (The problematic step)
        print("Waiting for modal and clicking 'LOGIN WITH KABAM'...")
        auth_tab = None
        for i in range(5):
            try:
                # We use context.expect_page to catch the popup
                with context.expect_page(timeout=10000) as new_page_info:
                    # Target the button by its specific class/style if possible, 
                    # but using a JS click is more reliable for bypass
                    page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const kabamBtn = buttons.find(b => b.innerText.includes('KABAM'));
                        if (kabamBtn) {
                            kabamBtn.click();
                        }
                    }""")
                auth_tab = new_page_info.value
                break
            except:
                print(f"Popup didn't trigger (Attempt {i+1}), retrying click...")
                time.sleep(2)

        if not auth_tab: 
            print("Failed to open the Kabam Auth window.")
            page.screenshot(path="error_screenshot.png")
            return False

        # 4. Fill Credentials
        print("Auth tab detected! Entering credentials...")
        auth_tab.wait_for_selector('input[type="email"]', timeout=20000)
        auth_tab.fill('input[type="email"]', EMAIL)
        auth_tab.fill('input[type="password"]', PASSWORD)
        
        # 5. Submission
        print("Submitting...")
        auth_tab.keyboard.press("Enter")
        
        # 6. Monitor for Success on the MAIN page
        print("Waiting for main page to reflect login...")
        success = False
        for _ in range(45):
            if page.locator("header button").filter(has_text=re.compile(r"CART", re.IGNORECASE)).is_visible():
                print("Login confirmed!")
                success = True
                break
            time.sleep(1)

        if not success:
            return False
        
        time.sleep(2) 
        context.storage_state(path=SESSION_FILE)
        return True

    except Exception as e:
        print(f"Error: {e}")
        page.screenshot(path="error_screenshot.png")
        return False
    finally:
        context.close()

def claim_rewards(page):
    print("Claiming rewards...")
    time.sleep(8)
    claimed = 0
    # Search for buttons
    while claimed < 20:
        btn = page.locator("button").filter(has_text=re.compile(r"GET FREE", re.IGNORECASE)).first
        if not btn.is_visible():
            break

        print(f"Claiming item #{claimed + 1}...")
        try:
            btn.click(force=True)
            time.sleep(5)
            page.keyboard.press("Escape") 
            time.sleep(2)
            claimed += 1
        except:
            page.reload()
            time.sleep(5)
    print(f"Finished. Total: {claimed}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        if login_and_save(browser):
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
            claim_rewards(page)
        
        browser.close()

if __name__ == "__main__":
    run()
