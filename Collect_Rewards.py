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

DEBUG_DIR = "./debug"
os.makedirs(DEBUG_DIR, exist_ok=True)


def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=15)
    except:
        pass


def save_debug_info(page, name):
    try:
        path = f"{DEBUG_DIR}/{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"[DEBUG] Screenshot saved: {path}")
    except Exception as e:
        print(f"[DEBUG] Screenshot FAILED for '{name}': {e}")


def save_html(page, name):
    try:
        path = f"{DEBUG_DIR}/{name}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"[DEBUG] HTML saved: {path}")
    except Exception as e:
        print(f"[DEBUG] HTML save FAILED for '{name}': {e}")


def check_auth(page):
    try:
        if page.get_by_text("LOG IN").first.is_visible():
            return False
        has_cart = page.get_by_role("button", name="CART").first.is_visible()
        has_name = page.locator("[class*='player-name']").first.is_visible()
        return has_cart or has_name
    except:
        return False


def login_and_save(browser):
    print("Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        print(f"Navigating to Xsolla auth URL...")
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        save_debug_info(page, "login_01_loaded")
        save_html(page, "login_01_loaded")

        print("Waiting for email input...")
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        save_debug_info(page, "login_02_filled")

        print("Clicking login button...")
        login_btn = page.get_by_role("button", name="Login")
        login_btn.click()

        print("Waiting for redirect to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(7000)
        save_debug_info(page, "login_03_redirected")
        save_html(page, "login_03_redirected")

        # Dismiss cookies
        try:
            cookie_btn = page.get_by_role("button", name="ACCEPT").first
            if cookie_btn.is_visible():
                cookie_btn.click()
                page.wait_for_timeout(2000)
                print("Cookie banner dismissed during login.")
        except:
            pass

        page.wait_for_timeout(3000)
        save_debug_info(page, "login_04_final_state")
        save_html(page, "login_04_final_state")

        login_still_visible = False
        try:
            login_still_visible = page.get_by_text("LOG IN").first.is_visible()
        except:
            pass

        if login_still_visible:
            raise Exception("Store still shows logged-out state after login attempt.")

        context.storage_state(path=SESSION_FILE)
        print("Login success and session saved.")

    except Exception as e:
        save_debug_info(page, "login_fail")
        save_html(page, "login_fail")
        raise e
    finally:
        context.close()


def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    save_debug_info(page, "store_01_initial")
    save_html(page, "store_01_initial")

    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
            print("Cookie banner dismissed.")
    except:
        pass

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
        print(f"[DEBUG] Found {count} potential buttons.")

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_enabled():
                    continue
                txt = btn.inner_text().upper()
                print(f"[DEBUG] Button #{i} text: '{txt}'")
                if "$" in txt or "MONTH" in txt:
                    print(f"[DEBUG] Skipping paid item: '{txt}'")
                    continue
                parent_text = btn.locator("xpath=..").inner_text().upper()
                if "MORE MARKET POINTS" in parent_text or ("GET" in parent_text and "POINTS" in parent_text):
                    print(f"[DEBUG] Skipping milestone: '{parent_text[:80]}'")
                    continue
                if btn.is_visible():
                    target_btn = btn
                    break
            except:
                continue

        if not target_btn:
            print("No more valid items to claim.")
            save_debug_info(page, f"store_no_more_items_{claimed}")
            break

        try:
            print(f"Claiming item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            save_debug_info(page, f"store_before_claim_{claimed + 1}")
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            save_debug_info(page, f"store_after_claim_{claimed + 1}")

            if page.get_by_text("LOGIN WITH KABAM").first.is_visible():
                print("Auth popup detected - stopping.")
                save_debug_info(page, "store_auth_popup")
                return "AUTH_FAILED"

            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception as e:
            print(f"[DEBUG] Click failed: {e}")
            save_debug_info(page, f"store_click_error_{claimed}")
            break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        send_telegram_msg("👀 No rewards found today.")
    return "SUCCESS"


def run():
    if not EMAIL or not PASSWORD:
        print("Missing credentials!")
        send_telegram_msg("⚠️ Missing EMAIL or PASSWORD environment variables!")
        return

    print(f"EMAIL is set: {'yes' if EMAIL else 'no'}")
    print(f"SESSION_FILE exists: {os.path.exists(SESSION_FILE)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None

        try:
            if not os.path.exists(SESSION_FILE):
                print("No session file found, logging in fresh...")
                login_and_save(browser)
            else:
                print("Session file found, skipping login.")

            context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
            page = context.new_page()

            print("Opening store...")
            page.goto(STORE_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            save_debug_info(page, "run_01_store_loaded")
            save_html(page, "run_01_store_loaded")

            if not check_auth(page):
                print("Session expired or invalid. Re-logging...")
                save_debug_info(page, "run_02_auth_check_failed")
                context.close()
                os.remove(SESSION_FILE)
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(5000)
                save_debug_info(page, "run_03_after_relogin")
                save_html(page, "run_03_after_relogin")

            claim_rewards(page)

        except Exception as e:
            print(f"Runtime error: {e}")
            send_telegram_msg(f"⚠️ Error: {str(e)[:200]}")
            if page:
                save_debug_info(page, "run_fatal_error")
                save_html(page, "run_fatal_error")
        finally:
            # Always write a heartbeat file so the artifact upload has at least something
            with open(f"{DEBUG_DIR}/run_log.txt", "w") as f:
                f.write(f"Script completed at {time.strftime('%Y-%m-%d %Human:%M:%S')}\n")
                f.write(f"SESSION_FILE existed at start: {os.path.exists(SESSION_FILE)}\n")
                f.write(f"EMAIL set: {'yes' if EMAIL else 'no'}\n")
            browser.close()
            print("Done.")


if __name__ == "__main__":
    run()
