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
# Updated Login URL provided by the user
NEW_LOGIN_URL = "https://kid.kabam.com/v2/oauth2/authorize?response_type=code&client_id=654630398575&redirect_uri=https%3A%2F%2Fstore.playcontestofchampions.com%23%2Foauth2%2Fcallback&scope=openid+profile+email&code_challenge=MF_j8Ytq0QB2NKV_JDsP0WtJfRcf7bW437ROps4-JhM&code_challenge_method=S256&state=AczZ7rw9W7oj9DY.lKKhvJ3BJ7aV%7EvBk"

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
        path = f"./{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"DEBUG: Screenshot saved as {path}")
    except Exception as e:
        print(f"DEBUG: Failed to save screenshot {name}: {e}")

def check_auth(page):
    try:
        # If we see a login button or 'SIGN IN', we aren't authorized
        login_visible = page.locator("button:has-text('LOGIN'), button:has-text('SIGN IN')").first.is_visible()
        if login_visible:
            return False
        # Look for the cart or player name container
        return page.locator("[class*='player-name']").first.is_visible() or \
               page.locator("[class*='CartButton']").first.is_visible()
    except:
        return False

def login_and_save(browser):
    print("ACTION: Starting Login Flow with new OAuth URL...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(NEW_LOGIN_URL, wait_until="networkidle", timeout=60000)
        
        # Wait for the email input specifically
        page.wait_for_selector('input[type="email"]', timeout=30000)
        
        print("ACTION: Filling credentials...")
        page.fill('input[type="email"]', EMAIL)
        time.sleep(1)
        page.fill('input[type="password"]', PASSWORD)
        time.sleep(1)
        
        # Take a snap after filling but before clicking
        save_debug_info(page, "0_filled_credentials")

        print("ACTION: Clicking orange Login button...")
        # Targeting the button specifically by its text 'Login'
        login_btn = page.get_by_role("button", name="Login", exact=True)
        login_btn.click()
        
        # Wait for the redirect to hit the store
        print("ACTION: Waiting for redirect to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        
        # Settle time for cookies/tokens to save in local storage
        time.sleep(15) 
        
        if check_auth(page):
            print("SUCCESS: Login verified.")
            context.storage_state(path=SESSION_FILE)
            save_debug_info(page, "1_login_verified_final")
        else:
            print("FAILURE: Redirected but check_auth failed.")
            save_debug_info(page, "ERROR_redirected_but_unauthorized")
            
    except Exception as e:
        save_debug_info(page, "ERROR_login_crash")
        print(f"CRASH: {str(e)}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("ACTION: Scanning for rewards...")
    time.sleep(10) # Long wait for JS hydration
    save_debug_info(page, "2_scanning_store")

    # Scroll heavily to ensure lazy-loaded items appear
    for i in range(12):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    claimed = 0
    # Common text for reward buttons
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
    
    buttons = page.locator(selector)
    count = buttons.count()
    print(f"DEBUG: {count} buttons found on store page.")

    for i in range(count):
        btn = buttons.nth(i)
        try:
            if not btn.is_visible() or not btn.is_enabled(): continue
            
            txt = btn.inner_text().upper()
            # If the session is dead, these buttons will say 'LOGIN'
            if "LOGIN" in txt or "$" in txt or "UNIT" in txt:
                continue

            print(f"ACTION: Claiming item #{claimed+1}...")
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            time.sleep(6)
            
            claimed += 1
            save_debug_info(page, f"claimed_item_{claimed}")
            
            # Dismiss success popup
            page.keyboard.press("Escape")
            time.sleep(2)
        except: continue

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found to claim.")
    return claimed

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        try:
            # Force a fresh login if no session exists
            if not os.path.exists(SESSION_FILE):
                login_and_save(browser)

            context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
            page = context.new_page()
            
            print("ACTION: Navigating to main store...")
            page.goto(STORE_URL, wait_until="networkidle")
            time.sleep(10)

            # Re-auth if the session died
            if not check_auth(page):
                print("WARNING: Session invalid. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                time.sleep(10)

            claim_rewards(page)
            
        except Exception as e:
            msg = f"⚠️ Script Error: {str(e)[:100]}"
            print(msg)
            send_telegram_msg(msg)
        finally:
            browser.close()

if __name__ == "__main__":
    run()
