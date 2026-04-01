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
            for tag in ["button", "span"]:
                el = page.locator(f"{tag}:has-text('{label}')").first
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(1500)
                    print(f"[COOKIE] Dismissed with '{label}'")
                    return
    except:
        pass


def dismiss_popup(page):
    """Close the success modal by clicking its backdrop."""
    try:
        backdrop = page.locator(".purchase-handler.modal-backdrop")
        if backdrop.count() > 0:
            backdrop.click(position={"x": 10, "y": 10})
            page.wait_for_timeout(2000)
            print("[CLAIM]   Dismissed success modal via backdrop click.")
            # Wait for modal to fully disappear
            page.wait_for_selector(".purchase-handler.modal-backdrop", state="hidden", timeout=5000)
            return True
    except Exception as e:
        print(f"[CLAIM]   Backdrop click failed: {e}")

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
    except:
        pass
    return False


def wait_for_store_ready(page):
    print("[NAV] Waiting for store SPA to settle...")
    for _ in range(30):
        url = page.url
        if "oauth2/callback" not in url and "store.playcontestofchampions.com" in url:
            break
        page.wait_for_timeout(1000)
        print(f"[NAV]   Still at: {url}")

    try:
        page.wait_for_selector("#header-bar", state="attached", timeout=20000)
    except:
        pass
    page.wait_for_timeout(3000)
    print(f"[NAV] Store ready at: {page.url}")


def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

    print("[LOGIN] Waiting for store JS to render...")
    page.wait_for_selector("span.button-login", state="attached", timeout=30000)
    page.wait_for_timeout(2000)
    dismiss_cookies(page)
    save_debug_info(page, "login_01_store")

    print("[LOGIN] Clicking LOGIN button via JS...")
    page.evaluate("document.querySelector('span.button-login').click()")

    print("[LOGIN] Waiting for redirect to kid.kabam.com...")
    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    print(f"[LOGIN] At: {page.url}")
    save_debug_info(page, "login_02_kabam")

    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"]', state="visible", timeout=20000)
    page.fill('input[type="email"]', EMAIL)
    page.wait_for_timeout(300)
    page.fill('input[type="password"]', PASSWORD)
    page.wait_for_timeout(300)
    save_debug_info(page, "login_03_filled")

    print("[LOGIN] Submitting...")
    try:
        page.locator('button[type="submit"]').first.click()
    except:
        page.keyboard.press("Enter")

    print("[LOGIN] Waiting for redirect back to store...")
    page.wait_for_url(
        re.compile(r"store\.playcontestofchampions\.com"),
        timeout=90000,
        wait_until="commit"
    )
    print(f"[LOGIN] Store URL detected: {page.url}")

    wait_for_store_ready(page)
    dismiss_cookies(page)
    page.wait_for_timeout(2000)
    save_debug_info(page, "login_04_post_redirect")
    save_html(page, "login_04_post_redirect")


def claim_rewards(page):
    print("[CLAIM] Starting reward scan...")

    for i in range(15):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.3)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    save_debug_info(page, "store_after_scroll")
    save_html(page, "store_after_scroll")

    # Count free items upfront
    initial_free = page.locator(".item-action-free").count()
    print(f"[CLAIM] Free items available: {initial_free}")

    if initial_free == 0:
        print("[CLAIM] No free items found — already claimed today or none available.")
        send_telegram_msg("✅ Store checked — no free items to claim today (already done or none available).")
        return

    claimed = 0
    consecutive_failures = 0
    max_consecutive_failures = 3

    while True:
        free_btns = page.locator(".item-action-free span.primary-button")
        count = free_btns.count()
        print(f"[CLAIM] Free buttons remaining: {count}")

        if count == 0:
            print("[CLAIM] All free items claimed!")
            break

        # Find a claimable button
        target_btn = None
        for i in range(count):
            btn = free_btns.nth(i)
            try:
                txt = btn.inner_text().strip().upper()
                print(f"[CLAIM]   Button #{i}: '{txt}'")
                if "LOGIN" in txt:
                    continue
                target_btn = btn
                break
            except:
                continue

        if not target_btn:
            print("[CLAIM] No claimable buttons found.")
            break

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save_debug_info(page, f"claim_{claimed + 1}_before")

            target_btn.click(force=True)
            page.wait_for_timeout(4000)
            save_debug_info(page, f"claim_{claimed + 1}_after")

            # Wait for and dismiss the success modal
            dismissed = dismiss_popup(page)
            page.wait_for_timeout(1500)

            # Check if the count actually decreased
            new_count = page.locator(".item-action-free span.primary-button").count()
            if new_count < count:
                claimed += 1
                consecutive_failures = 0
                print(f"[CLAIM]   ✅ Claimed! Total: {claimed}, Remaining: {new_count}")
            else:
                consecutive_failures += 1
                print(f"[CLAIM]   ⚠️ Count unchanged ({new_count}). Failure #{consecutive_failures}")
                save_debug_info(page, f"claim_stuck_{consecutive_failures}")
                save_html(page, f"claim_stuck_{consecutive_failures}")
                if consecutive_failures >= max_consecutive_failures:
                    print("[CLAIM]   Too many failures — stopping.")
                    break

        except Exception as e:
            consecutive_failures += 1
            print(f"[CLAIM] Error: {e}")
            save_debug_info(page, f"claim_error_{claimed}")
            if consecutive_failures >= max_consecutive_failures:
                break

    # Build informative summary
    remaining = page.locator(".item-action-free").count()
    if claimed > 0 and remaining == 0:
        msg = f"✅ Successfully claimed all {claimed} free reward(s)!"
    elif claimed > 0 and remaining > 0:
        msg = f"⚠️ Claimed {claimed} reward(s) but {remaining} still unclaimed — check debug."
    else:
        msg = "👀 No free rewards were claimed today."

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
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            login(page)

            try:
                context.storage_state(path=SESSION_FILE)
                print("[RUN] Session saved.")
            except Exception as e:
                print(f"[RUN] Session save failed (non-fatal): {e}")

            save_debug_info(page, "post_login_state")

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
