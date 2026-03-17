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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"DEBUG (No Telegram): {message}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=15)
    except:
        pass

def save_debug_info(page, name):
    try:
        page.screenshot(path=f"./{name}.png")
        with open(f"./{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except:
        pass

def handle_overlays(page):
    """מסירה באנרים של קוקיז או פופ-אפים שחוסמים את המסך"""
    try:
        # ניסיון ללחוץ על 'ACCEPT ALL'
        cookie_btn = page.locator("button:has-text('ACCEPT ALL')")
        if cookie_btn.is_visible():
            print("Cleaning cookie banner...")
            cookie_btn.click()
            page.wait_for_timeout(1000)
        
        # אם הבאנר עדיין שם - פשוט נמחק אותו דרך JS כדי שלא יפריע לקליקים
        page.evaluate("""
            const overlay = document.querySelector('.Banner__StyledBanner-sc-166puj-0');
            if (overlay) overlay.remove();
            const backdrop = document.querySelector('.CookieBanner__Backdrop-sc-');
            if (backdrop) backdrop.remove();
        """)
    except:
        pass

def is_logged_in(page):
    handle_overlays(page)
    try:
        if page.locator("text=LOG IN").is_visible():
            return False
        # מחפשים את שם המשתמש שלך (ZACHHENDE...) שמופיע בתמונה ששלחת
        return page.locator("button:has-text('ZACHHENDE')").is_visible() or page.locator(".u-text-player-name").is_visible()
    except:
        return False

def login_and_save(browser):
    print("Executing fresh login process...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        
        # וידוא שהעוגיות לא חוסמות את שדות הטקסט
        handle_overlays(page)
        
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_load_state("networkidle")
        
        if is_logged_in(page):
            context.storage_state(path=SESSION_FILE)
            print("Login successful.")
        else:
            save_debug_info(page, "login_failed_final_check")
            raise Exception("Auth completed but user session not detected.")
            
    except Exception as e:
        save_debug_info(page, "login_error_state")
        send_telegram_msg(f"❌ Login failed: {str(e)[:50]}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    handle_overlays(page)

    for i in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    claimed = 0
    while claimed < 15:
        handle_overlays(page)
        selector = "button:has-text('FREE'), button:has-text('GET')"
        buttons = page.locator(selector)
        
        target_btn = None
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            if btn.is_visible():
                text = btn.inner_text().upper()
                if "$" not in text:
                    target_btn = btn
                    break
        
        if not target_btn:
            break

        try:
            print(f"Attempting reward #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            page.wait_for_timeout(3000)

            if page.locator("text=LOGIN WITH KABAM").is_visible():
                print("Auth expired during claim.")
                return "AUTH_FAILED"

            page.keyboard.press("Escape")
            page.wait_for_timeout(1500)
            claimed += 1
        except:
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found today.")
    return "SUCCESS"

def run():
    if not EMAIL or not PASSWORD: return
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            page.goto(STORE_URL, wait_until="networkidle")
            
            if not is_logged_in(page):
                print("Session invalid. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")

            result = claim_rewards(page)
            
            if result == "AUTH_FAILED":
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                claim_rewards(page)

        except Exception as e:
            send_telegram_msg(f"⚠️ Error: {str(e)[:50]}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
