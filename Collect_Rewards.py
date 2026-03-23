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
    except: pass

def check_auth(page):
    """בדיקת לוגין בטוחה ללא Strict Mode Violation"""
    try:
        if page.get_by_text("LOG IN").first.is_visible():
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
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_timeout(7000) 
        context.storage_state(path=SESSION_FILE)
        print("Login success.")
    except Exception as e:
        save_debug_info(page, "login_fail")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    
    # סגירת קוקיז
    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
    except: pass

    # גלילה מסיבית כדי לוודא שכל האלמנטים נטענים
    for i in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    claimed = 0
    max_attempts = 15
    
    while claimed < max_attempts:
        # מחפש את כל המילים הרלוונטיות
        selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
        buttons = page.locator(selector)
        count = buttons.count()
        
        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                # 1. בדיקה אם הכפתור פעיל
                if not btn.is_enabled():
                    continue

                txt = btn.inner_text().upper()
                
                # 2. סינון רכישות בכסף או מנויים
                if "$" in txt or "MONTH" in txt:
                    continue
                
                # 3. סינון Milestones נעולים לפי הטקסט שמתחת לכפתור (כמו שראינו ב-claim_14.jpg)
                # אנחנו בודקים את הטקסט של ה-Container שעוטף את הכפתור
                parent_text = btn.locator("xpath=..").inner_text().upper()
                if "MORE MARKET POINTS" in parent_text or "GET" in parent_text and "POINTS" in parent_text:
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
            
            # בדיקת ניתוק סשן פתאומי
            if page.get_by_text("LOGIN WITH KABAM").first.is_visible():
                print("Auth popup detected - stopping.")
                return "AUTH_FAILED"

            page.keyboard.press("Escape")
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
        print("Missing credentials!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # לוגין ראשוני אם אין קובץ סשן
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print("Opening store...")
            page.goto(STORE_URL, wait_until="networkidle")
            page.wait_for_timeout(5000)
            
            # בדיקה אם באמת מחוברים (למקרה שהסשן בקובץ פג)
            if not check_auth(page):
                print("Session expired. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                page.wait_for_timeout(5000)

            claim_rewards(page)
            
        except Exception as e:
            print(f"Runtime error: {e}")
            send_telegram_msg(f"⚠️ Error: {str(e)[:100]}")
        finally:
            browser.close()
            print("Done.")

if __name__ == "__main__":
    run()
