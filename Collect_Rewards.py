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

# Telegram Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM: Secrets not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}
        requests.post(url, json=payload, timeout=15)
    except:
        pass

def save_debug_info(page, name):
    try:
        page.screenshot(path=f"./{name}.png")
        with open(f"./{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except:
        pass

def login_and_save(browser):
    print("Starting fresh login via Xsolla...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_selector("text=CART", timeout=40000)
        context.storage_state(path=SESSION_FILE)
        print("Login success.")
    except Exception as e:
        send_telegram_msg(f"❌ Login failed: {str(e)[:50]}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000) 
    
    # סגירת באנר עוגיות
    try:
        cookie_btn = page.locator("button:has-text('ACCEPT ALL')")
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(1000)
    except:
        pass

    for i in range(8):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

    save_debug_info(page, "3_store_view")
    
    claimed = 0
    # התיקון: במקום לולאת for קבועה, אנחנו מחפשים כפתור אחד בכל פעם עד שנגמרים הכפתורים
    while True:
        # מחפשים את הכפתור ה-FREE הבא שגלוי כרגע
        selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
        reward_buttons = page.locator(selector)
        
        target_btn = None
        for i in range(reward_buttons.count()):
            btn = reward_buttons.nth(i)
            btn_text = btn.inner_text().strip()
            # מוודא שזה לא בתשלום ושהכפתור גלוי
            if "$" not in btn_text and "MONTH" not in btn_text and btn.is_visible():
                target_btn = btn
                break
        
        if not target_btn:
            break  # אין יותר פרסים לאיסוף

        try:
            print(f"Claiming item: {target_btn.inner_text().strip()}")
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape") # סגירת הפופ-אפ שקופץ
            page.wait_for_timeout(2000)
            claimed += 1
        except:
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 Checked store - no free rewards found.")

def run():
    if not EMAIL or not PASSWORD:
        print("CRITICAL: Secrets missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print("Opening store...")
            page.goto(STORE_URL, wait_until="networkidle")
            save_debug_info(page, "0_landing")
            
            if page.locator("text=CART").count() == 0:
                print("Session expired. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")

            claim_rewards(page)
            
        except Exception as e:
            send_telegram_msg(f"⚠️ Runtime Error: {str(e)[:50]}")
        finally:
            browser.close()
            print("Done.")

if __name__ == "__main__":
    run()
