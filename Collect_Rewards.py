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
        page.screenshot(path=f"./{name}.png")
        print(f"DEBUG: Saved screenshot {name}.png")
    except Exception as e:
        print(f"DEBUG: Failed to save screenshot: {e}")

def check_auth(page):
    """בדיקה משולבת: מחפש שם משתמש או CART. אם מופיע LOG IN - לא מחובר."""
    if page.locator("text=LOG IN").is_visible():
        return False
    # מחפש את האלמנט של השם שלך או כפתור העגלה
    is_auth = page.locator("button:has-text('CART')").is_visible() or page.locator("[class*='player-name']").is_visible()
    return is_auth

def login_and_save(browser):
    print("Executing login_and_save...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        save_debug_info(page, "1_login_page")
        
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        
        print("Waiting for redirection back to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_timeout(7000) # זמן אקסטרה לטעינת הממשק
        
        save_debug_info(page, "2_after_login_redirect")
        context.storage_state(path=SESSION_FILE)
        print("Session state saved.")
    except Exception as e:
        save_debug_info(page, "login_critical_error")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    
    # סגירת באנר עוגיות אם מפריע
    try:
        cookie_btn = page.locator("button:has-text('ACCEPT ALL')")
        if cookie_btn.is_visible():
            print("Cookie banner detected, clicking Accept All...")
            cookie_btn.click()
            page.wait_for_timeout(2000)
    except: pass

    # גלילה לטעינת כל הכפתורים
    for i in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    save_debug_info(page, "3_store_scanned")
    
    claimed = 0
    max_attempts = 12
    
    while claimed < max_attempts:
        selector = "button:has-text('FREE'), button:has-text('GET')"
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"Found {count} potential reward buttons.")
        
        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            txt = btn.inner_text().upper()
            if "$" not in txt and "MONTH" not in txt and btn.is_visible():
                target_btn = btn
                break
        
        if not target_btn:
            print("No more valid buttons to click.")
            break

        try:
            btn_label = target_btn.inner_text().strip()
            print(f"Claiming: {btn_label}")
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            
            # בדיקת לוגין תוך כדי איסוף (הפופ-אפ הכתום)
            if page.locator("text=LOGIN WITH KABAM").is_visible():
                print("Auth popup appeared - session invalid!")
                return "AUTH_FAILED"

            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
            save_debug_info(page, f"claim_{claimed}_done")
        except Exception as e:
            print(f"Error during claim: {e}")
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found today.")
    return "SUCCESS"

def run():
    if not EMAIL or not PASSWORD:
        print("CRITICAL: Secrets missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        if not os.path.exists(SESSION_FILE):
            print("No session file found, starting login...")
            login_and_save(browser)

        context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print("Opening store...")
            page.goto(STORE_URL, wait_until="networkidle")
            page.wait_for_timeout(5000)
            
            save_debug_info(page, "0_initial_landing")
            
            if not check_auth(page):
                print("Auth check failed, re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                page.wait_for_timeout(5000)

            result = claim_rewards(page)
            if result == "AUTH_FAILED":
                print("Retrying after auth failure...")
                # כאן אפשר להוסיף לוגיקה של לוגין חוזר אם תרצה
            
        except Exception as e:
            print(f"Runtime Exception: {e}")
            send_telegram_msg(f"⚠️ Error: {str(e)[:50]}")
        finally:
            browser.close()
            print("Done.")

if __name__ == "__main__":
    run()
