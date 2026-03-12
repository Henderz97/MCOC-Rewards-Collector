import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD") 
SESSION_FILE = "kabam_session.json"
HEADLESS = True  
# ---------------------

def login_and_save(browser):
    print("Starting login process...")
    # Add a slightly longer timeout for GitHub's network
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=60000)

        # 1. Clear Overlays
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=5000)
        except:
            pass

        # 2. Open Modal
        print("Opening login modal...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        page.wait_for_timeout(5000) 

        # 3. Handle Kabam Popup with Retry Loop
        print("Attempting to open Kabam Auth window...")
        auth_page = None
        for attempt in range(3):
            try:
                with context.expect_page(timeout=15000) as new_page_info:
                    # Target the specific orange login button via text and role
                    page.evaluate("() => { const b = document.querySelector('button[class*=\"orange\"], .modal-content button'); if(b) b.click(); }")
                auth_page = new_page_info.value
                break
            except:
                print(f"Popup didn't open (Attempt {attempt + 1}/3), retrying click...")
                page.wait_for_timeout(3000)

        if not auth_page:
            raise Exception("Failed to open Kabam Auth popup after 3 attempts.")

        auth_page.wait_for_load_state("networkidle")

        # 4. Fill & Enter
        print("Filling credentials...")
        auth_page.wait_for_selector('input[type="email"]', timeout=20000)
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        
        print("Submitting via Enter...")
        auth_page.keyboard.press("Enter")

        # 5. Verify Success on Main Page
        print("Waiting for session confirmation...")
        # We wait for the 'CART' button or the 'LOG IN' button to disappear
        page.wait_for_selector("button:has-text('CART')", timeout=45000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login success. Session saved.")
    except Exception as e:
        print(f"Login failed: {e}")
        # Optional: page.screenshot(path="login_error.png")
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_timeout(10000) # Give the store plenty of time to load
    
    claimed = 0
    # Specifically target 'GET FREE'
    while claimed < 20:
        buttons = page.get_by_role("button", name=re.compile("get free", re.I))
        
        if buttons.count() == 0:
            print("No 'GET FREE' buttons found.")
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception as e:
            print(f"Claim failed: {e}. Reloading...")
            page.reload()
            page.wait_for_timeout(8000)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    with sync_playwright() as p:
        # slow_mo helps prevent the site from flagging us as a bot in GitHub
        browser = p.chromium.launch(
            headless=HEADLESS,
            slow_mo=100, 
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        login_and_save(browser)

        if os.path.exists(SESSION_FILE):
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()
            try:
                page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
                claim_rewards(page)
            except Exception as e:
                print(f"Runtime error: {e}")
            finally:
                context.close()
        else:
            print("Failed to create session file. Cannot proceed.")

        browser.close()
        print("Process complete.")

if __name__ == "__main__":
    run()
