import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
# We keep this True in code, but the Workflow will handle the "Display"
HEADLESS = True 

def login_and_save(browser):
    print("Starting login process...")
    # Masking the automation footprint
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        has_touch=True,
        java_script_enabled=True
    )
    page = context.new_page()

    try:
        print("Navigating to store...")
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle", timeout=90000)

        # Handle Cookie Banner quickly
        try:
            page.get_by_role("button", name=re.compile("accept|agree|allow|ok", re.I)).click(timeout=10000)
        except:
            pass

        print("Locating Login button...")
        # Sometimes the button is inside an iframe or needs a moment to be 'stable'
        login_btn = page.get_by_role("button", name=re.compile("log in", re.I)).first
        login_btn.wait_for(state="visible", timeout=30000)

        print("Opening Login Popup...")
        # We'll try to click and wait for the page simultaneously
        with context.expect_page(timeout=90000) as new_page_info:
            login_btn.click(delay=150) # Small delay to simulate human click
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Filling credentials...")
        # Using exact selectors for the Kabam auth page
        auth_page.get_by_label("Email").fill(EMAIL)
        auth_page.get_by_label("Password").fill(PASSWORD)
        auth_page.get_by_role("button", name=re.compile("log in", re.I)).click()

        # Wait for the main page to show "LOG OUT" (meaning login succeeded)
        print("Verifying successful login...")
        page.wait_for_selector("button:has-text('LOG OUT')", timeout=90000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login successful. Session saved.")
    except Exception as e:
        page.screenshot(path="login_debug.png")
        if 'auth_page' in locals():
             auth_page.screenshot(path="auth_debug.png")
        print(f"Login failed: {e}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_timeout(5000)
    
    claimed = 0
    # The store is very dynamic; we refresh to ensure we catch everything
    for attempt in range(2):
        print(f"Claim attempt pass {attempt + 1}...")
        # Look for 'FREE' or 'CLAIM' buttons
        buttons = page.locator("button").filter(has_text=re.compile(r"Free|Claim", re.I))
        
        count = buttons.count()
        if count == 0:
            print("No rewards visible.")
            break

        for i in range(count):
            try:
                target = buttons.nth(i)
                if target.is_visible():
                    print(f"Clicking reward {claimed + 1}...")
                    target.click(timeout=10000)
                    page.wait_for_timeout(3000)
                    page.keyboard.press("Escape") # Clear the 'Success' popup
                    claimed += 1
            except:
                continue
        
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(5000)
            
    print(f"Process ended. Total items claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Error: KABAM_EMAIL or KABAM_PASSWORD environment variables are missing.")
        return

    with sync_playwright() as p:
        # Launching with extra args to dodge detection
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        # Apply the session
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Check if we are still logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible():
                print("Session expired or invalid. Attempting re-login...")
                login_and_save(browser)
                # Reload with new session
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
