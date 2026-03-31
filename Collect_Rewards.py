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
    except Exception as e:
        print(f"[TELEGRAM] Failed: {e}")


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


def dismiss_cookies(page):
    try:
        for label in ["ACCEPT ALL", "ACCEPT", "Accept All", "Accept"]:
            btn = page.get_by_role("button", name=label).first
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(1500)
                print(f"[COOKIE] Dismissed with '{label}'")
                return
    except:
        pass


def check_auth(page):
    """Returns True if the store shows a logged-in state."""
    try:
        # Look for LOGIN buttons — if they exist, we're logged out
        login_buttons = page.locator("a:has-text('LOGIN'), button:has-text('LOGIN'), button:has-text('LOG IN')")
        count = login_buttons.count()
        print(f"[AUTH] Found {count} LOGIN button(s) on page")
        if count > 0:
            return False
        return True
    except Exception as e:
        print(f"[AUTH] check_auth error: {e}")
        return False


def claim_rewards(page):
    print("[CLAIM] Starting reward scan...")
    page.wait_for_load_state("domcontentloaded")
    dismiss_cookies(page)

    # Scroll to load all lazy elements
    for i in range(12):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.4)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    save_debug_info(page, "store_after_scroll")
    save_html(page, "store_after_scroll")

    claimed = 0
    max_attempts = 15

    while claimed < max_attempts:
        # Find all free/claim buttons
        selector = "button:has-text('FREE'), button:has-text('CLAIM')"
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"[CLAIM] Found {count} FREE/CLAIM buttons.")

        # Also log all LOGIN buttons for context
        login_count = page.locator("button:has-text('LOGIN'), a:has-text('LOGIN')").count()
        print(f"[CLAIM] Found {login_count} LOGIN buttons (items needing purchase/auth).")

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_enabled() or not btn.is_visible():
                    continue

                txt = btn.inner_text().strip().upper()
                print(f"[CLAIM] Checking button #{i}: '{txt}'")

                if "$" in txt or "MONTH" in txt:
                    print(f"[CLAIM]   → Skipping (paid)")
                    continue

                parent_text = ""
                try:
                    parent_text = btn.locator("xpath=ancestor::*[3]").inner_text().upper()
                except:
                    pass

                if "MORE MARKET POINTS" in parent_text or ("GET" in parent_text and "POINTS" in parent_text):
                    print(f"[CLAIM]   → Skipping (milestone gate)")
                    continue

                target_btn = btn
                print(f"[CLAIM]   → Selected as target")
                break
            except Exception as e:
                print(f"[CLAIM]   → Error: {e}")
                continue

        if not target_btn:
            print("[CLAIM] No more claimable items found.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save_debug_info(page, f"claim_{claimed + 1}_before")
            target_btn.click(force=True)
            page.wait_for_timeout(5000)
            save_debug_info(page, f"claim_{claimed + 1}_after")

            # Dismiss any confirmation/result popup
            page.keyboard.press("Escape")
            page.wait_for_timeout(1500)
            claimed += 1

        except Exception as e:
            print(f"[CLAIM] Click error: {e}")
            save_debug_info(page, f"claim_error_{claimed}")
            break

    msg = f"✅ Claimed {claimed} rewards!" if claimed > 0 else "👀 No claimable rewards found today."
    send_telegram_msg(msg)
    print(f"[CLAIM] Done. {msg}")


def run():
    print(f"EMAIL is set: {'yes' if EMAIL else 'NO'}")
    print(f"SESSION_FILE existed at start: {os.path.exists(SESSION_FILE)}")

    if not EMAIL or not PASSWORD:
        print("Missing credentials!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )

        # Use ONE context for the entire flow — login + store in the same session
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Step 1: Go to the Xsolla/Kabam login page
            print("[RUN] Navigating to auth URL...")
            page.goto(XSOLLA_AUTH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            save_debug_info(page, "login_01_loaded")
            save_html(page, "login_01_loaded")
            print(f"[RUN] URL after auth nav: {page.url}")

            # Step 2: Fill credentials
            print("[RUN] Waiting for email input...")
            page.wait_for_selector('input[type="email"]', timeout=30000)
            page.fill('input[type="email"]', EMAIL)
            page.wait_for_timeout(300)
            page.fill('input[type="password"]', PASSWORD)
            page.wait_for_timeout(300)
            save_debug_info(page, "login_02_filled")

            # Step 3: Submit
            print("[RUN] Submitting login form...")
            try:
                page.get_by_role("button", name="Login").click()
            except:
                page.keyboard.press("Enter")

            # Step 4: Wait for redirect back to store
            print("[RUN] Waiting for store redirect...")
            page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=90000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(6000)  # Extra wait for auth cookies to settle
            print(f"[RUN] Redirected to: {page.url}")

            dismiss_cookies(page)
            page.wait_for_timeout(2000)

            save_debug_info(page, "login_03_post_redirect")
            save_html(page, "login_03_post_redirect")

            # Step 5: Verify auth in the SAME context/page
            is_auth = check_auth(page)
            print(f"[RUN] Auth check: {is_auth}")
            save_debug_info(page, "login_04_auth_check")

            if not is_auth:
                print("[RUN] Still not authenticated after login. Aborting.")
                send_telegram_msg("⚠️ Login failed — still logged out after redirect. Check debug screenshots.")
                return

            # Step 6: Save session for potential future use
            context.storage_state(path=SESSION_FILE)
            print("[RUN] Session saved.")

            # Step 7: Claim rewards on the same page/context
            print("[RUN] Proceeding to claim rewards...")
            # Navigate to store root to ensure clean state
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            dismiss_cookies(page)
            save_debug_info(page, "store_01_loaded")

            claim_rewards(page)

        except Exception as e:
            print(f"[RUN] FATAL ERROR: {e}")
            send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
            try:
                save_debug_info(page, "fatal_error")
                save_html(page, "fatal_error")
            except:
                pass
        finally:
            context.close()
            browser.close()
            print("[RUN] Done.")


if __name__ == "__main__":
    run()
