import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
STORE_URL = "https://store.playcontestofchampions.com/"
XSOLLA_AUTH_URL = "https://login.xsolla.com/api/social/kabam/login_redirect?projectId=2c9de8c3-c57c-4bfe-83e6-20416f767517&login_url=https%3A%2F%2Fstore.playcontestofchampions.com&payload=%7B%7D&locale=en_US&trackId=&login_url=https%3A%2F%2Flogin-widget.xsolla.com%2Flatest%2Fsocial-auth-succeed%3FprojectId%3D2c9de8c3-c57c-4bfe-83e6-20416f767517%26callbackUrl%3Dhttps%3A%2F%2Fstore.playcontestofchampions.com"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("DEBUG: Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=10)
    except Exception as e:
        print(f"DEBUG: Telegram failed: {e}")

def save_debug_info(page, name):
    try:
        page.screenshot(path=f"./{name}.png")
        with open(f"./{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except:
        pass

def login_and_save(browser):
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
    except Exception as e:
        send_telegram_msg(f"❌ Login failed: {str(e)[:50]}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
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
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
    reward_buttons = page.locator(selector)
    count = reward_buttons.count()
    claimed = 0
    for i in range(count):
        try:
            btn = reward_buttons.nth(i)
            btn_text = btn.inner_text().strip()
            if "$" in btn_text or "MONTH" in btn_text:
                continue
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            claimed += 1
        except:
            continue
    
    # שינוי כאן: שולח הודעה בכל מקרה כדי שנוכל לבדוק שהבוט עובד
    if claimed > 0:
        send_telegram_msg(f"✅ Claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 Checked for rewards, but found none today.")

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
            save_debug_info(page, "0_landing")
            if page.locator("text=CART").count() == 0:
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
