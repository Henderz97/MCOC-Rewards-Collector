import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
STORE_URL = "https://store.playcontestofchampions.com/"
# Xsolla Auth URL is used for the initial login redirect
XSOLLA_AUTH_URL = "https://login.xsolla.com/api/social/kabam/login_redirect?projectId=2c9de8c3-c57c-4bfe-83e6-20416f767517&login_url=https%3A%2F%2Fstore.playcontestofchampions.com&payload=%7B%7D&locale=en_US&trackId=&login_url=https%3A%2F%2Flogin-widget.xsolla.com%2Flatest%2Fsocial-auth-succeed%3FprojectId%3D2c9de8c3-c57c-4bfe-83e6-20416f767517%26callbackUrl%3Dhttps%3A%2F%2Fstore.playcontestofchampions.com"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=15)
    except: pass

def save_debug_info(page, name):
    try:
        page.screenshot(path=f"./{name}.png")
    except: pass

def check_auth(page):
    """Checks if the user is logged in by looking for the CART button or player name."""
    try:
        # If 'LOG IN' is visible, we are definitely not authenticated
        if page.get_by_text("LOG IN").first.is_visible():
            return False
        
        # Check for elements that only appear when logged in
        is_auth = page.get_by_role("button", name="CART").first.is_visible() or \
                  page.locator("[class*='player-name']").first.is_visible()
        return is_auth
    except:
        return False

def login_and_save(browser):
    """Performs a full login flow and saves the session to a JSON file."""
    print("Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        
        # Wait for the redirect back to the store
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_timeout(7000) 
        
        # Save the authentication state (cookies, local storage)
        context.storage_state(path=SESSION_FILE)
        print(f"Login success. Session saved to {SESSION_FILE}")
    except Exception as e:
        save_debug_info(page, "login_fail")
        print(f"Login failed: {e}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    
    # Accept cookies if the popup appears
    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
    except: pass

    # Scroll to trigger lazy-loading of store items
    for _ in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    claimed = 0
    max_attempts = 15
    
    while claimed < max_attempts:
        selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
        buttons = page.locator(selector)
        count = buttons.count()
        
        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_enabled(): continue

                txt = btn.inner_text().upper()
                
                # Filter out paid items
                if "$" in txt or "MONTH" in txt: continue
                
                # Filter out locked milestone points
                parent_text = btn.locator("xpath=..").inner_text().upper()
                if "MORE MARKET POINTS" in parent_text or ("GET" in parent_text and "POINTS" in parent_text):
                    continue

                if btn.is_visible():
                    target_btn = btn
                    break
            except: continue
        
        if not target_btn:
            print("No more valid items to claim.")
            break

        try:
            print(f"Claiming item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            
            # Check if we got kicked to a login screen mid-process
            if page.get_by_text("LOGIN WITH KABAM").first.is_visible():
                print("Auth popup detected - stopping.")
                return "AUTH_FAILED"

            page.keyboard.press("Escape") # Close any "Item Claimed" popups
            page.wait_for_timeout(2000)
            claimed += 1
            save_debug_info(page, f"claimed_{claimed}")
        except:
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found today.")
    return "SUCCESS"

def run():
    if not EMAIL or not PASSWORD:
        print("Error: KABAM_EMAIL or KABAM_PASSWORD environment variables are missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Step 1: Check if we have a session file. If not, log in.
        if not os.path.exists(SESSION_FILE):
            print("No session file found.")
            login_and_save(browser)

        # Step 2: Open browser with the existing session
        context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print("Opening store...")
            page.goto(STORE_URL, wait_until="networkidle")
            page.wait_for_timeout(5000)
            
            # Step 3: Validate if session is still alive
            if not check_auth(page):
                print("Session expired or invalid. Re-logging...")
                context.close()
                login_and_save(browser)
                
                # Re-open context with the NEW session file created by login_and_save
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                page.wait_for_timeout(5000)

            # Step 4: Run the claiming logic
            result = claim_rewards(page)
            
            # Final check: if claiming failed due to auth, you could retry once here.
            if result == "AUTH_FAILED":
                print("Final auth check failed during claiming.")

        except Exception as e:
            print(f"Runtime error: {e}")
            send_telegram_msg(f"⚠️ Error: {str(e)[:100]}")
        finally:
            browser.close()
            print("Process finished.")

if __name__ == "__main__":
    run()
