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
    """שולחת הודעה לטלגרם אם הוגדרו טוקנים"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("DEBUG: Telegram notifications not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"DEBUG: Failed to send Telegram message: {e}")

def save_debug_info(page, name):
    """שומר צילום מסך וקובץ HTML לדיבאג מלא"""
    try:
        page.screenshot(path=f"./{name}.png")
        with open(f"./{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"DEBUG: Saved {name}.png and {name}.html")
    except Exception as e:
        print(f"DEBUG Error: Could not save debug info for {name}: {e}")

def login_and_save(browser):
    print("Starting fresh login via Xsolla...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        print("Navigating to Xsolla Auth Page...")
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        
        print("Filling credentials...")
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        
        save_debug_info(page, "1_login_page_filled")
        page.keyboard.press("Enter")

        print("Waiting for redirection back to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_selector("text=CART", timeout=40000)
        
        context.storage_state(path=SESSION_FILE)
        print("SUCCESS: Session saved.")
    except Exception as e:
        send_telegram_msg(f"❌ Login failed! {str(e)[:50]}")
        save_debug_info(page, "error_login_step")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000) 

    # ניקוי באנר עוגיות (Cookies)
    try:
        cookie_btn = page.locator("button:has-text('ACCEPT ALL')")
        if cookie_btn.is_visible():
            print("Clicking Cookie Banner...")
            cookie_btn.click()
            page.wait_for_timeout(1000)
    except:
        pass

    for i in range(8):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

    save_debug_info(page, "3_store_scanned_view")

    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
    reward_buttons = page.locator(selector)
    count = reward_buttons.count()
    print(f"Found {count} potential reward buttons.")

    claimed = 0
    for i in range(count):
        try:
            btn = reward_buttons.nth(i)
            btn_text = btn.inner_text().strip()
            if "$" in btn_text or "MONTH" in btn_text:
                continue

            print(f"Claiming: '{btn_text}'")
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            btn.click(force=True)
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            claimed += 1
        except Exception as e:
            print(f"Could not claim item {i}: {e}")

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    print(f"Done. Claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("MISSING SECRETS")
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
            save_debug_info(page, "0_landing_check")
            
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
            save_debug_info(page, "fatal_runtime_error")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
