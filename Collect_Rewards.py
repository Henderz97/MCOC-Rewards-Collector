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
    print("Starting login process in Stealth Mode...")
    # Use a real Chrome User-Agent to avoid being flagged as a bot
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent=user_agent
    )
    page = context.new_page()

    try:
        # Step 1: Navigate with a longer timeout
        page.goto("https://store.playcontestofchampions.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # Step 2: Clear Cookies
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=5000)
        except: pass

        # Step 3: Open the Login Modal
        print("Clicking header login...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()
        time.sleep(5) 

        # Step 4: The 'Stealth' Popup Click
        print("Attempting to trigger popup...")
        auth_page = None
        for attempt in range(3):
            try:
                with context.expect_page(timeout=20000) as new_page_info:
                    # We use a real mouse click on the coordinates of the button 
                    # as it's harder to detect than a JS .click()
                    page.get_by_text("LOGIN WITH KABAM").click(force=True, delay=150)
                auth_page = new_page_info.value
                break
            except Exception as e:
                print(f"Popup fail (Attempt {attempt + 1}): Retrying...")
                page.reload() # Sometimes a fresh page load helps reset bot detection
                time.sleep(5)
                page.get_by_role("button", name=re.compile("log in", re.I)).click()
                time.sleep(3)

        if not auth_page:
            raise Exception("Kabam Auth window refused to open. Bot detection likely.")

        # Step 5: Fill Credentials
        print("Auth window opened! Submitting credentials...")
        auth_page.wait_for_selector('input[type="email"]', timeout=20000)
        auth_page.fill('input[type="email"]', EMAIL, delay=100)
        auth_page.fill('input[type="password"]', PASSWORD, delay=100)
        auth_page.keyboard.press("Enter")

        # Step 6: Verify Success
        print("Waiting for main page to sync...")
        # Check for the CART or your username appearing
        page.wait_for_selector("button:has-text('CART')", timeout=60000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login success! Session cached.")
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        return False
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for 'GET FREE' items...")
    time.sleep(10)
    
    claimed = 0
    while claimed < 20:
        # Find all buttons that say 'GET FREE'
        buttons = page.locator("button").filter(has_text=re.compile("GET FREE", re.I))
        
        if buttons.count() == 0:
            print("No more free rewards found.")
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            target = buttons.first
            target.click(force=True)
            time.sleep(5)
            page.keyboard.press("Escape")
            time.sleep(3)
            claimed += 1
        except:
            page.reload()
            time.sleep(8)
            
    print(f"Mission accomplished. Total: {claimed}")

def run():
    with sync_playwright() as p:
        # Adding more flags to bypass headless detection
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        if login_and_save(browser):
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()
            try:
                page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
                claim_rewards(page)
            except Exception as e:
                print(f"Claiming error: {e}")
            finally:
                context.close()
        else:
            print("Could not establish a session.")

        browser.close()

if __name__ == "__main__":
    run()
