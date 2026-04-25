import os
import re
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
STORE_URL = "https://store.playcontestofchampions.com/"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DEBUG_DIR = "./debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

FREE_BTN_SELECTOR = ".item-action-free span.primary-button"
SOLD_OUT_SELECTOR = ".item-action-free .item-sold-out"


def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"},
            timeout=15,
        )
    except Exception as e:
        print(f"[TELEGRAM] Failed: {e}")


def save_debug(page, name):
    try:
        page.screenshot(path=f"{DEBUG_DIR}/{name}.png", full_page=True)
    except Exception as e:
        print(f"[DEBUG] Screenshot failed for '{name}': {e}")


def save_html(page, name):
    try:
        with open(f"{DEBUG_DIR}/{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print(f"[DEBUG] HTML save failed for '{name}': {e}")


def dismiss_cookies(page):
    for label in ["ACCEPT ALL", "ACCEPT", "Accept All", "Accept"]:
        for tag in ["button", "span"]:
            try:
                el = page.locator(f"{tag}:has-text('{label}')").first
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(1000)
                    print(f"[COOKIE] Dismissed with '{label}'")
                    return
            except Exception:
                pass


def dismiss_popup(page):
    # Milestone modal
    try:
        modal = page.locator(".modal-backdrop .modal-bundle")
        if modal.count() > 0 and modal.first.is_visible():
            btn = page.locator(".modal-bundle span.primary-button").first
            if btn.count() > 0:
                btn.click(force=True)
                page.wait_for_timeout(1500)
                print("[CLAIM] Dismissed milestone modal.")
                return True
    except Exception as e:
        print(f"[CLAIM] Milestone modal handling failed: {e}")

    # Purchase success modal
    try:
        modal = page.locator(".purchase-handler.modal-backdrop")
        if modal.count() > 0 and modal.first.is_visible():
            modal.first.click(position={"x": 10, "y": 10})
            page.wait_for_timeout(1500)
            print("[CLAIM] Dismissed success modal.")
            return True
    except Exception as e:
        print(f"[CLAIM] Success modal handling failed: {e}")

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
    return False


def wait_for_store_ready(page):
    print("[NAV] Waiting for store to settle...")
    for _ in range(30):
        if "oauth2/callback" not in page.url and "store.playcontestofchampions.com" in page.url:
            break
        page.wait_for_timeout(1000)

    try:
        page.wait_for_selector("#header-bar", state="attached", timeout=20000)
    except Exception:
        pass

    page.wait_for_timeout(2000)
    print(f"[NAV] Store ready at: {page.url}")


def count_claimable(page):
    """Return count of visible FREE buttons that aren't login/sold-out prompts."""
    locator = page.locator(FREE_BTN_SELECTOR)
    total = locator.count()
    claimable = 0
    for i in range(total):
        try:
            btn = locator.nth(i)
            txt = btn.inner_text().strip().upper()
            if "LOGIN" not in txt and "SOLD" not in txt and btn.is_visible():
                claimable += 1
        except Exception:
            pass
    return claimable


def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

    page.wait_for_selector("span.button-login", state="visible", timeout=30000)
    dismiss_cookies(page)

    print("[LOGIN] Clicking LOGIN...")
    page.evaluate("document.querySelector('span.button-login').click()")

    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"]', state="visible", timeout=20000)
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)

    try:
        page.locator('button[type="submit"]').first.click()
    except Exception:
        page.keyboard.press("Enter")

    print("[LOGIN] Waiting for store redirect...")
    page.wait_for_url(
        re.compile(r"store\.playcontestofchampions\.com"),
        timeout=90000,
        wait_until="commit",
    )
    wait_for_store_ready(page)
    dismiss_cookies(page)


def claim_rewards(page):
    print("[CLAIM] Waiting for store items to load...")

    # Wait for at least one item to appear instead of scrolling blindly
    try:
        page.wait_for_selector(".item-action-free", state="attached", timeout=15000)
    except Exception:
        print("[CLAIM] No free items found on page.")
        send_telegram_msg("✅ Store checked — no free items visible today.")
        return

    # Scroll to bottom once to trigger lazy-loading, then back to top
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    initial_claimable = count_claimable(page)
    sold_out = page.locator(SOLD_OUT_SELECTOR).count()
    print(f"[CLAIM] Found {initial_claimable} claimable, {sold_out} sold out")

    if initial_claimable == 0:
        send_telegram_msg(
            f"✅ Store checked — nothing to claim ({sold_out} sold out/reset pending)."
        )
        return

    claimed = 0
    consecutive_failures = 0
    max_failures = 3

    while consecutive_failures < max_failures:
        free_btns = page.locator(FREE_BTN_SELECTOR)
        total = free_btns.count()

        # Find first claimable button
        target = None
        for i in range(total):
            try:
                btn = free_btns.nth(i)
                txt = btn.inner_text().strip().upper()
                if "LOGIN" not in txt and "SOLD" not in txt and btn.is_visible():
                    target = btn
                    break
            except Exception:
                continue

        if target is None:
            print("[CLAIM] No more claimable items.")
            break

        try:
            print(f"[CLAIM] Claiming item #{claimed + 1}...")
            target.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            target.click(force=True)
            page.wait_for_timeout(3500)

            dismiss_popup(page)
            page.wait_for_timeout(1000)

            new_count = count_claimable(page)
            if new_count < (initial_claimable - claimed):
                claimed += 1
                consecutive_failures = 0
                print(f"[CLAIM] ✅ Claimed! Total: {claimed}, remaining: {new_count}")
            else:
                consecutive_failures += 1
                print(f"[CLAIM] ⚠️ Count unchanged — failure #{consecutive_failures}")
                if consecutive_failures >= max_failures:
                    save_debug(page, "claim_stuck")
                    save_html(page, "claim_stuck")

        except Exception as e:
            consecutive_failures += 1
            print(f"[CLAIM] Error: {e}")
            if consecutive_failures >= max_failures:
                save_debug(page, "claim_error")

    remaining = count_claimable(page)
    sold_out = page.locator(SOLD_OUT_SELECTOR).count()

    if claimed > 0 and remaining == 0:
        msg = f"✅ Claimed all {claimed} free reward(s)!"
        if sold_out:
            msg += f" ({sold_out} sold out — will reset later)"
    elif claimed > 0:
        msg = f"⚠️ Claimed {claimed} but {remaining} still unclaimed — check debug."
    else:
        msg = f"👀 Nothing claimed today."
        if sold_out:
            msg += f" ({sold_out} sold out — will reset later)"

    send_telegram_msg(msg)
    print(f"[CLAIM] Done. {msg}")


def run():
    if not EMAIL or not PASSWORD:
        print("[RUN] Missing credentials — aborting.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            login(page)
            claim_rewards(page)

        except Exception as e:
            print(f"[RUN] FATAL ERROR: {e}")
            send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
            save_debug(page, "fatal_error")
            save_html(page, "fatal_error")

        finally:
            context.close()
            browser.close()
            print("[RUN] Done.")


if __name__ == "__main__":
    run()
