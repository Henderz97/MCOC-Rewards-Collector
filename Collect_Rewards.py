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
    except:
        pass


def save_debug_info(page, name):
    try:
        path = f"./{name}.png"
        page.screenshot(path=path, full_page=True)
        print(f"[DEBUG] Screenshot saved: {path}")
    except Exception as e:
        print(f"[DEBUG] Screenshot failed for '{name}': {e}")


def save_html(page, name):
    try:
        path = f"./{name}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"[DEBUG] HTML saved: {path}")
    except Exception as e:
        print(f"[DEBUG] HTML save failed for '{name}': {e}")


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
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        save_debug_info(page, "login_01_loaded")
        save_html(page, "login_01_loaded")

        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        save_debug_info(page, "login_02_filled")

        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_timeout(7000)
        save_debug_info(page, "login_03_success")
        save_html(page, "login_03_success")

        context.storage_state(path=SESSION_FILE)
        print("Login success.")
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

    # Close cookie banner
    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
            print("Cookie banner dismissed.")
    except:
        pass

    # Scroll to load all elements
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
            page.wait_for_timeout(5000)
            save_debug_info(page, "run_01_store_loaded")
            save_html(page, "run_01_store_loaded")

            if not check_auth(page):
                print("Session expired. Re-logging...")
                save_debug_info(page, "run_02_auth_failed")
                context.close()
                login_and_save(browser)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                page.wait_for_timeout(5000)
                save_debug_info(page, "run_03_after_relogin")

            claim_rewards(page)

        except Exception as e:
            print(f"Runtime error: {e}")
            save_debug_info(page, "run_error")
            save_html(page, "run_error")
            send_telegram_msg(f"⚠️ Error: {str(e)[:100]}")
        finally:
            browser.close()
            print("Done.")


if __name__ == "__main__":
    run()
