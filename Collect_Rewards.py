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
    # Using a real user agent helps bypass some bot detection
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="domcontentloaded")

        # Handle Cookie Consent
        try:
            page.get_by_role("button", name=re.compile("accept|agree|allow", re.I)).click(timeout=5000)
        except:
            pass

        print("Opening Login...")
        # Trigger the popup
        with context.expect_page() as new_page_info:
            page.get_by_role("button", name=re.compile("log in", re.I)).first.click()
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Filling credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        auth_page.get_by_role("button", name=re.compile("log in", re.I)).click()

        # Wait for the popup to close and redirect to finish
        page.wait_for_selector("text=LOG OUT", timeout=60000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_timeout(5000)
    
    claimed = 0
    # The store often requires a few seconds to load the 'Free' tags
    for _ in range(5): 
        # Target buttons that specifically say 'Claim' or 'Free'
        buttons = page.get_by_role("button", name=re.compile("Get Free|Claim", re.I))
        count = buttons.count()
        
        if count == 0:
            break

        for i in range(count):
            try:
                print(f"Attempting to claim item {claimed + 1}...")
                buttons.nth(i).click()
                page.wait_for_timeout(3000)
                # Close the 'Success' modal
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                claimed += 1
            except:
                continue
        
        page.reload() # Refresh to see if new tiers unlocked
        page.wait_for_timeout(3000)

    print(f"Finished! Total items claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Error: KABAM_EMAIL or KABAM_PASSWORD secrets are missing.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # Check if session exists
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(
            storage_state=SESSION_FILE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/")
            
            # Verify if still logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible():
                print("Session expired. Re-authenticating...")
                login_and_save(browser)
                # Reload with new state
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto("https://store.playcontestofchampions.com/")

            claim_rewards(page)
        except Exception as e:
            print(f"Runtime error: {e}")
            page.screenshot(path="error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
