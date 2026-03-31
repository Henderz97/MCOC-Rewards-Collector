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
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=15)
    except Exception as e:
        print(f"[TELEGRAM] Failed to send message: {e}")


def save_debug_info(page, name):
    try:
        path = f"./{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"[DEBUG] Screenshot saved: {path}")
    except Exception as e:
        print(f"[DEBUG] Screenshot FAILED for '{name}': {e}")


def save_html(page, name):
    try:
        path = f"./{name}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"[DEBUG] HTML saved: {path}")
    except Exception as e:
        print(f"[DEBUG] HTML save FAILED for '{name}': {e}")


def check_auth(page):
    try:
        login_visible = page.locator("text=LOG IN").first.is_visible()
        print(f"[AUTH] 'LOG IN' text visible: {login_visible}")
        if login_visible:
            return False

        has_cart = False
        has_name = False
        try:
            has_cart = page.get_by_role("button", name="CART").first.is_visible()
        except:
            pass
        try:
            has_name = page.locator("[class*='player-name']").first.is_visible()
        except:
            pass

        print(f"[AUTH] has_cart={has_cart}, has_name={has_name}")
        return has_cart or has_name
    except Exception as e:
        print(f"[AUTH] check_auth error: {e}")
        return False


def login_and_save(browser):
    print("[LOGIN] Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        print(f"[LOGIN] Navigating to XSOLLA_AUTH_URL...")
        page.goto(XSOLLA_AUTH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        save_debug_info(page, "login_01_loaded")
        save_html(page, "login_01_loaded")

        print(f"[LOGIN] Current URL: {page.url}")
        print("[LOGIN] Waiting for email input...")
        page.wait_for_selector('input[type="email"]', timeout=30000)

        page.fill('input[type="email"]', EMAIL)
        page.wait_for_timeout(500)
        page.fill('input[type="password"]', PASSWORD)
        page.wait_for_timeout(500)
        save_debug_info(page, "login_02_filled")

        print("[LOGIN] Clicking login button...")
        try:
            login_btn = page.get_by_role("button", name="Login")
            login_btn.click()
        except Exception as e:
            print(f"[LOGIN] Button click failed, trying Enter: {e}")
            page.keyboard.press("Enter")

        print("[LOGIN] Waiting for redirect to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)

        print(f"[LOGIN] Redirected to: {page.url}")
        save_debug_info(page, "login_03_redirected")
        save_html(page, "login_03_redirected")

        # Dismiss cookie banner
        try:
            cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
            if cookie_btn.is_visible():
                cookie_btn.click()
                page.wait_for_timeout(2000)
                print("[LOGIN] Cookie banner dismissed.")
        except:
            pass

        page.wait_for_timeout(3000)
        save_debug_info(page, "login_04_final")
        save_html(page, "login_04_final")

        context.storage_state(path=SESSION_FILE)
        print("[LOGIN] Session saved successfully.")

    except Exception as e:
        print(f"[LOGIN] FAILED: {e}")
        save_debug_info(page, "login_fail")
        save_html(page, "login_fail")
        raise e
    finally:
        context.close()


def claim_rewards(page):
    print("[CLAIM] Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    save_debug_info(page, "store_01_initial")
    save_html(page, "store_01_initial")

    # Dismiss cookie banner
    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
            print("[CLAIM] Cookie banner dismissed.")
    except:
        pass

    # Scroll to load all elements
    print("[CLAIM] Scrolling to load all elements...")
    for i in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)

    save_debug_info(page, "store_02_after_scroll")
    save_html(page, "store_02_after_scroll")

    claimed = 0
    max_attempts = 15

    while claimed < max_attempts:
        selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"[CLAIM] Found {count} potential buttons.")

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_enabled():
                    print(f"[CLAIM] Button #{i} is disabled, skipping.")
                    continue

                txt = btn.inner_text().upper()
                print(f"[CLAIM] Button #{i} text: '{txt}'")

                if "$" in txt or "MONTH" in txt:
                    print(f"[CLAIM] Skipping paid item: '{txt}'")
                    continue

                parent_text = btn.locator("xpath=..").inner_text().upper()
                if "MORE MARKET POINTS" in parent_text or ("GET" in parent_text and "POINTS" in parent_text):
                    print(f"[CLAIM] Skipping milestone: '{parent_text[:80]}'")
                    continue

                if btn.is_visible():
                    target_btn = btn
                    print(f"[CLAIM] Targeting button #{i}: '{txt}'")
                    break
            except Exception as e:
                print(f"[CLAIM] Error inspecting button #{i}: {e}")
                continue

        if not target_btn:
            print("[CLAIM] No more valid items to claim.")
            save_debug_info(page, f"store_no_more_items_{claimed}")
            break

        try:
            print(f"[CLAIM] Claiming item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            save_debug_info(page, f"store_before_claim_{claimed + 1}")
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            save_debug_info(page, f"store_after_claim_{claimed + 1}")

            try:
                if page.get_by_text("LOGIN WITH KABAM").first.is_visible():
                    print("[CLAIM] Auth popup detected - stopping.")
                    save_debug_info(page, "store_auth_popup")
                    return "AUTH_FAILED"
            except:
                pass

            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1

        except Exception as e:
            print(f"[CLAIM] Click failed on item #{claimed + 1}: {e}")
            save_debug_info(page, f"store_click_error_{claimed}")
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found today.")
    return "SUCCESS"


def run():
    print("[RUN] Script started.")
    print(f"[RUN] EMAIL set: {bool(EMAIL)}, PASSWORD set: {bool(PASSWORD)}")
    print(f"[RUN] SESSION_FILE exists: {os.path.exists(SESSION_FILE)}")

    if not EMAIL or not PASSWORD:
        print("[RUN] Missing credentials! Exiting.")
        return

    browser = None
    page = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            print("[RUN] Browser launched.")

            # Always do a fresh login — don't trust cached session
            print("[RUN] Forcing fresh login (ignoring any cached session)...")
            login_and_save(browser)

            context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
            page = context.new_page()

            print("[RUN] Opening store...")
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            save_debug_info(page, "run_01_store_loaded")
            save_html(page, "run_01_store_loaded")
            print(f"[RUN] Store URL: {page.url}")

            is_auth = check_auth(page)
            print(f"[RUN] Auth check result: {is_auth}")
            save_debug_info(page, "run_02_auth_check")

            if not is_auth:
                print("[RUN] Not authenticated after login — check login_fail screenshots.")
                send_telegram_msg("⚠️ Auth failed even after fresh login. Check debug screenshots.")
                return

            claim_rewards(page)

    except Exception as e:
        print(f"[RUN] FATAL ERROR: {e}")
        send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
        # Try to save a screenshot even in fatal cases
        if page:
            try:
                save_debug_info(page, "run_fatal_error")
                save_html(page, "run_fatal_error")
            except:
                pass
    finally:
        print("[RUN] Done.")


if __name__ == "__main__":
    run()
