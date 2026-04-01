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
            page.wait_for_timeout(1500)
            print("[CLAIM]   Dismissed success modal via backdrop click.")
            return
    except Exception as e:
        print(f"[CLAIM]   Backdrop click failed: {e}")

    # Fallback: Escape key
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except:
        pass


def wait_for_store_ready(page):
    """Wait for the SPA to finish rendering after navigation."""
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

    all_actions = page.locator(".item-actions")
    print(f"[CLAIM] Total item action containers: {all_actions.count()}")
    for i in range(all_actions.count()):
        try:
            cls = all_actions.nth(i).get_attribute("class") or ""
            txt = all_actions.nth(i).inner_text().strip()
            print(f"[CLAIM]   Action #{i} class='{cls}' text='{txt}'")
        except:
            pass

    free_actions = page.locator(".item-action-free")
    print(f"[CLAIM] Free item containers: {free_actions.count()}")

    claimed = 0
    max_attempts = 20
    prev_free_count = -1

    while claimed < max_attempts:
        free_btns = page.locator(".item-action-free span.primary-button")
        count = free_btns.count()
        print(f"[CLAIM] Round {claimed + 1}: Found {count} free button(s).")

        if count == 0:
            print("[CLAIM] No free buttons found — done.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        # Stuck detection
        if count == prev_free_count:
            print("[CLAIM] Count unchanged — still stuck after dismiss attempt. Stopping.")
            save_debug_info(page, f"store_stuck_at_{claimed}_claims")
            save_html(page, f"store_stuck_at_{claimed}_claims")
            break
        prev_free_count = count

        target_btn = None
        for i in range(count):
            btn = free_btns.nth(i)
            try:
                txt = btn.inner_text().strip().upper()
                print(f"[CLAIM]   Button #{i}: '{txt}'")
                if "LOGIN" in txt:
                    print(f"[CLAIM]   → Skipping (LOGIN)")
                    continue
                target_btn = btn
                print(f"[CLAIM]   → Selected")
                break
            except Exception as e:
                print(f"[CLAIM]   → Error reading button #{i}: {e}")
                continue

        if not target_btn:
            print("[CLAIM] All free buttons show LOGIN — done.")
            save_debug_info(page, f"store_done_after_{claimed}_claims")
            break

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save_debug_info(page, f"claim_{claimed + 1}_before")

            target_btn.click(force=True)
            page.wait_for_timeout(4000)
            save_debug_info(page, f"claim_{claimed + 1}_after")
            save_html(page, f"claim_{claimed + 1}_after")

            dismiss_popup(page)
            page.wait_for_timeout(2000)

            # Confirm claim worked by checking count decreased
            new_count = page.locator(".item-action-free span.primary-button").count()
            print(f"[CLAIM]   Free buttons after claim: {new_count} (was {count})")
            if new_count < count:
                claimed += 1
                prev_free_count = new_count
                print(f"[CLAIM]   ✅ Confirmed! Total claimed: {claimed}")
            else:
                print(f"[CLAIM]   ⚠️ Count unchanged after dismiss — trying harder.")
                save_debug_info(page, f"claim_{claimed + 1}_stuck")
                save_html(page, f"claim_{claimed + 1}_stuck")
                # Try clicking backdrop again then escape
                try:
                    backdrop = page.locator(".purchase-handler.modal-backdrop")
                    if backdrop.count() > 0:
                        backdrop.click(position={"x": 10, "y": 10})
                        page.wait_for_timeout(1000)
                except:
                    pass
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                page.mouse.click(100, 100)
                page.wait_for_timeout(1000)
                final_count = page.locator(".item-action-free span.primary-button").count()
                if final_count == count:
                    print("[CLAIM]   Still stuck — stopping.")
                    break
                else:
                    claimed += 1
                    prev_free_count = final_count

        except Exception as e:
            print(f"[CLAIM] Error on item #{claimed + 1}: {e}")
            save_debug_info(page, f"claim_error_{claimed}")
            save_html(page, f"claim_error_{claimed}")
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

            try:
                context.storage_state(path=SESSION_FILE)
                print("[RUN] Session saved.")
            except Exception as e:
                print(f"[RUN] Session save failed (non-fatal): {e}")

            save_debug_info(page, "post_login_state")
            save_html(page, "post_login_state")

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
