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
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

        # 1. Clear Overlays
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=3000)
        except:
            pass

        # 2. Click Login
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        time.sleep(5) 

        # 3. Handle Kabam Popup
        with context.expect_page() as new_page_info:
            page.evaluate("() => document.querySelector('button[class*=\"orange\"], .modal-content button')?.click()")
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        # 4. Fill & Enter
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        auth_page.keyboard.press("Enter")

        # 5. Verify Redirect
        page.wait_for_selector("button:has-text('CART')", timeout=30000)
        context.storage_state(path=SESSION_FILE)
        print("Login success. Session cached.")
    except Exception as e:
        print(f"Login failed: {e}")
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    time.sleep(8) # Extra time for GitHub's slower network
    
    claimed = 0
    while claimed < 20:
        buttons = page.get_by_role("button", name=re.compile("get free", re.I))
        
        if buttons.count() == 0:
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            time.sleep(5)
            page.keyboard.press("Escape")
            time.sleep(2)
            claimed += 1
        except:
            page.reload()
            time.sleep(5)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        # On GitHub Actions, we always start fresh
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
