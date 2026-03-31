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
        if page.get_by_text("LOG IN").first.is_visible():
            return False
        is_auth = page.get_by_role("button", name="CART").first.is_visible() or \
                  page.locator("[class*='player-name']").first.is_visible()
        return is_auth
    except:
        return False

def login_and_save(browser):
    print("ACTION: Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        time.sleep(10) 
        
        save_debug_info(page, "1_login_success_verification")
        context.storage_state(path=SESSION_FILE)
        print("SUCCESS: Session saved.")
    except Exception as e:
        save_debug_info(page, "ERROR_login_failed")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("ACTION: Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    time.sleep(8) # Wait for rewards to load
    
    save_debug_info(page, "2_pre_scan_view")

    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            time.sleep(2)
    except: pass

    # Scroll to reveal all items
    for i in range(8):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.8)

    save_debug_info(page, "3_after_scrolling_view")

    claimed = 0
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM'), [role='button']:has-text('FREE')"
    
    while claimed < 15:
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"DEBUG: Found {count} potential buttons...")

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible(): continue
                
                txt = btn.inner_text().upper()
                parent_txt = btn.locator("xpath=..").inner_text().upper()

                if "$" in txt or "UNIT" in txt or "MONTH" in txt: continue
                if "MORE MARKET POINTS" in parent_txt: continue

                target_btn = btn
                break
            except: continue

        if not target_btn:
            print("INFO: No valid claimable items found.")
            save_debug_info(page, "4_final_scan_nothing_left")
            break

        try:
            print(f"ACTION: Claiming item #{claimed+1}...")
            target_btn.scroll_into_view_if_needed()
            time.sleep(1)
            target_btn.click(force=True)
            time.sleep(6)
            
            claimed += 1
            save_debug_info(page, f"5_claimed_item_{claimed}")
            
            page.keyboard.press("Escape")
            time.sleep(2)
        except Exception as e:
            print(f"ERROR: Claiming failed: {e}")
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found. Check debug screenshots.")
    return claimed

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        if not os.path.exists(SESSION_FILE):
            print("INFO: No session file. Logging in...")
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        try:
            print("ACTION: Navigating to Store...")
            page.goto(STORE_URL, wait_until="networkidle")
            time.sleep(6)

            if not check_auth(page):
                print("WARNING: Session expired. Refreshing...")
                save_debug_info(page, "0_session_expired_fallback")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1280, "height": 720})
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                time.sleep(6)

            claim_rewards(page)
            
        except Exception as e:
            print(f"CRITICAL: {e}")
            save_debug_info(page, "ERROR_critical_runtime")
        finally:
            browser.close()
            print("INFO: Process complete.")

if __name__ == "__main__":
    run()
