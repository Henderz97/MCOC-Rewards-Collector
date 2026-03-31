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
    """Saves both a screenshot and the HTML content for deep debugging."""
    try:
        path = f"./{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"Screenshot saved: {path}")
        # Optional: Save HTML if you want to inspect the code later
        # with open(f"./{name}.html", "w", encoding="utf-8") as f:
        #     f.write(page.content())
    except Exception as e:
        print(f"Failed to save debug info {name}: {e}")

def check_auth(page):
    try:
        # If 'LOG IN' is visible, we are definitely not authenticated
        login_btn = page.get_by_text("LOG IN").first
        if login_btn.is_visible():
            return False
        
        is_auth = page.get_by_role("button", name="CART").first.is_visible() or \
                  page.locator("[class*='player-name']").first.is_visible()
        return is_auth
    except:
        return False

def login_and_save(browser):
    print("Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        
        # Wait for redirect
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_timeout(10000) 
        
        save_debug_info(page, "after_login_success")
        context.storage_state(path=SESSION_FILE)
        print("Login success state saved.")
    except Exception as e:
        save_debug_info(page, "login_fail_trace")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    time.sleep(5) # Extra wait for JavaScript elements
    
    save_debug_info(page, "pre_scan_state")

    # Try to close popups/cookies
    try:
        page.get_by_role("button", name="ACCEPT ALL").first.click(timeout=3000)
    except: pass

    # Scrolling to load all items
    for i in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

    claimed = 0
    # Targeted selectors for 'FREE' rewards
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM'), [role='button']:has-text('FREE')"
    
    while claimed < 15:
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"Found {count} potential buttons...")

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible(): continue
                
                txt = btn.inner_text().upper()
                parent_txt = btn.locator("xpath=..").inner_text().upper()

                # Filter logic
                if "$" in txt or "UNIT" in txt or "MONTH" in txt: continue
                if "MORE MARKET POINTS" in parent_txt: continue

                target_btn = btn
                break
            except: continue

        if not target_btn:
            print("No valid claimable items found.")
            save_debug_info(page, "final_scan_nothing_found")
            break

        try:
            print(f"Claiming item #{claimed+1}...")
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            time.sleep(5)
            
            save_debug_info(page, f"claimed_item_{claimed+1}")
            
            # Close popup
            page.keyboard.press("Escape")
            time.sleep(2)
            claimed += 1
        except Exception as e:
            print(f"Error claiming: {e}")
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    return claimed

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        try:
            print("Navigating to store...")
            page.goto(STORE_URL, wait_until="networkidle")
            time.sleep(5)

            if not check_auth(page):
                print("Session expired. Refreshing...")
                save_debug_info(page, "expired_session_view")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")

            claim_rewards(page)
            
        except Exception as e:
            print(f"Critical Error: {e}")
            save_debug_info(page, "critical_error_state")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
