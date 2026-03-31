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


def check_logged_in(page):
    """Check if the store now shows us as logged in (no top-level LOGIN button)."""
    try:
        # After login the top nav LOGIN button disappears
        top_login = page.locator("header button:has-text('LOGIN'), nav button:has-text('LOGIN'), header a:has-text('LOGIN')").first
        if top_login.is_visible():
            print("[AUTH] Top nav LOGIN button still visible — not logged in.")
            return False
        print("[AUTH] No top nav LOGIN button — appears logged in.")
        return True
    except Exception as e:
        print(f"[AUTH] check_logged_in error: {e}")
        return False


def login(page):
    """Click the store LOGIN button and complete the kid.kabam.com OAuth flow."""
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    dismiss_cookies(page)
    save_debug_info(page, "login_01_store")
    save_html(page, "login_01_store")
    print(f"[LOGIN] Store URL: {page.url}")

    # Log all buttons visible on the store for diagnosis
    all_btns = page.locator("button")
    print(f"[LOGIN] Buttons on store page: {all_btns.count()}")
    for i in range(min(all_btns.count(), 20)):
        try:
            print(f"[LOGIN]   btn #{i}: '{all_btns.nth(i).inner_text().strip()}'")
        except:
            pass

    # Click the top-level LOGIN button (not an item button)
    print("[LOGIN] Looking for top-level LOGIN button...")
    # Try several selectors for the main login button
    login_clicked = False
    for selector in [
        "header button:has-text('LOGIN')",
        "nav button:has-text('LOGIN')",
        "header a:has-text('LOGIN')",
        "nav a:has-text('LOGIN')",
        ".header button:has-text('LOGIN')",
        ".nav button:has-text('LOGIN')",
        "button:has-text('LOG IN')",
        "a:has-text('LOG IN')",
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible():
                print(f"[LOGIN] Found login button with selector: {selector}")
                btn.click()
                login_clicked = True
                break
        except:
            continue

    if not login_clicked:
        # Fallback: click the very first LOGIN button/link on the page
        print("[LOGIN] No header LOGIN found, trying first LOGIN element on page...")
        try:
            btn = page.locator("button:has-text('LOGIN'), a:has-text('LOGIN')").first
            btn.click()
            login_clicked = True
        except Exception as e:
            print(f"[LOGIN] Could not find any LOGIN button: {e}")
            save_debug_info(page, "login_no_button_found")
            save_html(page, "login_no_button_found")
            raise Exception("Could not find LOGIN button on store page")

    # Wait for redirect to kid.kabam.com
    print("[LOGIN] Waiting for redirect to kid.kabam.com...")
    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    print(f"[LOGIN] At kid.kabam.com: {page.url}")
    save_debug_info(page, "login_02_kabam")
    save_html(page, "login_02_kabam")

    # Fill credentials
    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"], input[name="email"], input[name="username"]', timeout=20000)

    # Try email field
    for email_selector in ['input[type="email"]', 'input[name="email"]', 'input[name="username"]']:
        try:
            if page.locator(email_selector).first.is_visible():
                page.fill(email_selector, EMAIL)
                print(f"[LOGIN] Filled email with selector: {email_selector}")
                break
        except:
            continue

    page.wait_for_timeout(300)

    # Try password field
    for pwd_selector in ['input[type="password"]', 'input[name="password"]']:
        try:
            if page.locator(pwd_selector).first.is_visible():
                page.fill(pwd_selector, PASSWORD)
                print(f"[LOGIN] Filled password with selector: {pwd_selector}")
                break
        except:
            continue

    page.wait_for_timeout(300)
    save_debug_info(page, "login_03_filled")

    # Submit
    print("[LOGIN] Submitting...")
    submitted = False
    for btn_selector in [
        'button[type="submit"]',
        "button:has-text('Login')",
        "button:has-text('Sign In')",
        "button:has-text('SIGN IN')",
        "button:has-text('Continue')",
    ]:
        try:
            btn = page.locator(btn_selector).first
            if btn.is_visible():
                btn.click()
                submitted = True
                print(f"[LOGIN] Submitted with: {btn_selector}")
                break
        except:
            continue

    if not submitted:
        page.keyboard.press("Enter")
        print("[LOGIN] Submitted with Enter key")

    # Wait for redirect back to store
    print("[LOGIN] Waiting for redirect back to store...")
    page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=90000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5000)
    print(f"[LOGIN] Back at store: {page.url}")

    dismiss_cookies(page)
    page.wait_for_timeout(2000)

    save_debug_info(page, "login_04_post_redirect")
    save_html(page, "login_04_post_redirect")


def claim_rewards(page):
    print("[CLAIM] Starting reward scan...")
    page.wait_for_load_state("domcontentloaded")

    # Scroll to load all lazy elements
    for i in range(15):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.3)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    save_debug_info(page, "store_after_scroll")
    save_html(page, "store_after_scroll")

    # Log ALL buttons for diagnosis
    all_buttons = page.locator("button")
    total = all_buttons.count()
    print(f"[CLAIM] Total buttons on page: {total}")
    for i in range(min(total, 40)):
        try:
            txt = all_buttons.nth(i).inner_text().strip()
            visible = all_buttons.nth(i).is_visible()
            print(f"[CLAIM]   Button #{i}: '{txt}' visible={visible}")
        except:
            pass

    claimed = 0
    max_attempts = 20

    while claimed < max_attempts:
        # After login, free items should show GET / FREE / CLAIM buttons
        selector = "button:has-text('GET'), button:has-text('FREE'), button:has-text('CLAIM')"
        buttons = page.locator(selector)
        count = buttons.count()
        print(f"[CLAIM] Found {count} claimable button(s).")

        if count == 0:
            print("[CLAIM] No claimable buttons found.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible() or not btn.is_enabled():
                    continue
                txt = btn.inner_text().strip().upper()
                if "$" in txt or "€" in txt or "£" in txt:
                    continue
                target_btn = btn
                print(f"[CLAIM] Targeting button #{i}: '{txt}'")
                break
            except:
                continue

        if not target_btn:
            print("[CLAIM] No valid target found.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        try:
            print(f"[CLAIM] Claiming item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save_debug_info(page, f"claim_{claimed + 1}_before")
            target_btn.click(force=True)
            page.wait_for_timeout(6000)
            save_debug_info(page, f"claim_{claimed + 1}_after")
            save_html(page, f"claim_{claimed + 1}_after")

            # Dismiss popup
            for close_label in ["CLOSE", "OK", "COLLECT", "CONFIRM", "DONE"]:
                try:
                    close_btn = page.get_by_role("button", name=close_label).first
                    if close_btn.is_visible():
                        close_btn.click()
                        page.wait_for_timeout(1000)
                        print(f"[CLAIM] Dismissed popup with '{close_label}'")
                        break
                except:
                    pass

            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1

        except Exception as e:
            print(f"[CLAIM] Error on item #{claimed + 1}: {e}")
            save_debug_info(page, f"claim_error_{claimed}")
            break

    msg = f"✅ Claimed {claimed} rewards!" if claimed > 0 else "👀 No free rewards to claim today."
    send_telegram_msg(msg)
    print(f"[CLAIM] {msg}")


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

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Login via the store's own LOGIN button → kid.kabam.com flow
            login(page)

            # Verify login worked
            is_auth = check_logged_in(page)
            print(f"[RUN] Auth check: {is_auth}")
            save_debug_info(page, "auth_check")

            if not is_auth:
                send_telegram_msg("⚠️ Login failed — store still shows logged out.")
                return

            # Save session
            context.storage_state(path=SESSION_FILE)
            print("[RUN] Session saved.")

            # Claim rewards on current page (already at store after redirect)
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
