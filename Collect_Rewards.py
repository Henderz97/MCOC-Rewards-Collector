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
            # cookies may be a button or span
            for tag in ["button", "span"]:
                el = page.locator(f"{tag}:has-text('{label}')").first
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(1500)
                    print(f"[COOKIE] Dismissed with '{label}'")
                    return
    except:
        pass


def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

    # Wait for the JS app to render — specifically wait for the LOGIN span to appear
    print("[LOGIN] Waiting for store to render LOGIN button...")
    page.wait_for_selector("span.button-login", timeout=30000)
    page.wait_for_timeout(1000)
    dismiss_cookies(page)
    save_debug_info(page, "login_01_store")
    save_html(page, "login_01_store")

    # Click the top nav LOGIN span (class="primary-button button-login")
    print("[LOGIN] Clicking LOGIN button...")
    page.locator("span.button-login").first.click()

    # Wait for redirect to kid.kabam.com
    print("[LOGIN] Waiting for redirect to kid.kabam.com...")
    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    print(f"[LOGIN] At: {page.url}")
    save_debug_info(page, "login_02_kabam")
    save_html(page, "login_02_kabam")

    # Fill credentials
    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"], input[name="email"]', timeout=20000)
    page.fill('input[type="email"]', EMAIL)
    page.wait_for_timeout(300)
    page.fill('input[type="password"]', PASSWORD)
    page.wait_for_timeout(300)
    save_debug_info(page, "login_03_filled")

    # Submit
    print("[LOGIN] Submitting...")
    try:
        page.locator('button[type="submit"]').first.click()
    except:
        page.keyboard.press("Enter")

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

    # Scroll to load all lazy elements
    for i in range(15):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.3)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    save_debug_info(page, "store_after_scroll")
    save_html(page, "store_after_scroll")

    # Free items have class "item-action-free" on their action container
    # The clickable element inside is a span.primary-button
    # After login these should show GET/CLAIM/FREE instead of LOGIN
    # Log what we see for diagnosis
    free_actions = page.locator(".item-action-free")
    print(f"[CLAIM] Found {free_actions.count()} free item action(s).")
    for i in range(free_actions.count()):
        try:
            txt = free_actions.nth(i).inner_text().strip()
            print(f"[CLAIM]   Free item #{i}: '{txt}'")
        except:
            pass

    claimed = 0
    max_attempts = 20

    while claimed < max_attempts:
        # Target the clickable span inside free item actions
        free_btns = page.locator(".item-action-free span.primary-button")
        count = free_btns.count()
        print(f"[CLAIM] Found {count} free item button(s).")

        if count == 0:
            print("[CLAIM] No free item buttons found.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        target_btn = None
        for i in range(count):
            btn = free_btns.nth(i)
            try:
                if not btn.is_visible():
                    continue
                txt = btn.inner_text().strip().upper()
                print(f"[CLAIM]   Checking free button #{i}: '{txt}'")
                # Skip if still showing LOGIN (means not logged in properly)
                # Skip if disabled
                if "LOGIN" in txt:
                    print(f"[CLAIM]   → Still showing LOGIN, skipping")
                    continue
                target_btn = btn
                print(f"[CLAIM]   → Selected")
                break
            except:
                continue

        if not target_btn:
            print("[CLAIM] No claimable free items found (all may be LOGIN or already claimed).")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save_debug_info(page, f"claim_{claimed + 1}_before")
            target_btn.click(force=True)
            page.wait_for_timeout(6000)
            save_debug_info(page, f"claim_{claimed + 1}_after")
            save_html(page, f"claim_{claimed + 1}_after")

            # Dismiss any popup
            for close_label in ["CLOSE", "OK", "COLLECT", "CONFIRM", "DONE"]:
                try:
                    # Try both span and button
                    for tag in ["span", "button"]:
                        el = page.locator(f"{tag}:has-text('{close_label}')").first
                        if el.is_visible():
                            el.click()
                            page.wait_for_timeout(1000)
                            print(f"[CLAIM]   Dismissed popup with '{close_label}'")
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
            login(page)

            # Verify login — button-login span should be gone, replaced by user info
            page.wait_for_timeout(2000)
            login_still_visible = page.locator("span.button-login").count() > 0
            print(f"[RUN] Login button still visible: {login_still_visible}")
            save_debug_info(page, "auth_check")

            if login_still_visible:
                send_telegram_msg("⚠️ Login failed — store still shows LOGIN button.")
                return

            context.storage_state(path=SESSION_FILE)
            print("[RUN] Session saved.")

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
