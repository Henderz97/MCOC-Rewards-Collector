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
    try:
        path = f"./{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"DEBUG: Screenshot saved as {path}")
    except Exception as e:
        print(f"DEBUG: Failed to save screenshot {name}: {e}")

def check_auth(page):
    try:
        # Check if the 'LOGIN' button in top nav is missing
        nav_login = page.locator("button:has-text('LOGIN')").first
        if nav_login.is_visible():
            return False
        return page.locator("[class*='player-name']").first.is_visible() or \
               page.get_by_role("button", name="CART").first.is_visible()
    except:
        return False

def login_and_save(browser):
    print("ACTION: Starting Login Flow...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('input[type="email"]', timeout=30000)
        
        # Filling info
        page.fill('input[type="email"]', EMAIL)
        time.sleep(1)
        page.fill('input[type="password"]', PASSWORD)
        time.sleep(1)
        
        # Updated selector for the actual Login button
        # Based on your image, it is a button with text "Login"
        print("ACTION: Clicking Login button...")
        login_btn = page.get_by_role("button", name="Login", exact=True)
        login_btn.click()
        
        # Wait for redirect to complete
        print("ACTION: Waiting for redirect...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        time.sleep(15) # Give it time to load the items after redirect
        
        if check_auth(page):
            print("SUCCESS: Logged in successfully.")
            context.storage_state(path=SESSION_FILE)
            save_debug_info(page, "1_login_verified")
        else:
            print("FAILURE: Login clicked but redirect didn't result in auth.")
            save_debug_info(page, "ERROR_login_failed_after_click")
            
    except Exception as e:
        save_debug_info(page, "ERROR_login_crash")
        print(f"CRASH: {str(e)}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("ACTION: Scanning rewards...")
    time.sleep(8)
    save_debug_info(page, "2_store_view")

    for i in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    claimed = 0
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
    buttons = page.locator(selector)
    count = buttons.count()
    
    for i in range(count):
        btn = buttons.nth(i)
        try:
            if not btn.is_visible(): continue
            txt = btn.inner_text().upper()
            if "LOGIN" in txt or "$" in txt or "UNIT" in txt: continue

            print(f"ACTION: Claiming item #{claimed+1}...")
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            time.sleep(5)
            
            claimed += 1
            save_debug_info(page, f"claimed_{claimed}")
            page.keyboard.press("Escape")
            time.sleep(2)
        except: continue

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards claimed. Check logs.")
    return claimed

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        try:
            if not os.path.exists(SESSION_FILE):
                login_and_save(browser)

            context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
            page = context.new_page()
            page.goto(STORE_URL, wait_until="networkidle")
            time.sleep(8)

            if not check_auth(page):
                print("WARNING: Session invalid. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                time.sleep(8)

            claim_rewards(page)
            
        except Exception as e:
            error_msg = f"⚠️ Critical Script Error: {str(e)[:100]}"
            print(error_msg)
            send_telegram_msg(error_msg)
        finally:
            browser.close()

if __name__ == "__main__":
    run()
