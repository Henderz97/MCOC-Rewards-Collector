import os
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
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


def save_debug(page, name):
    try:
        page.screenshot(path=f"{DEBUG_DIR}/{name}.png", full_page=True)
    except Exception as e:
        print(f"[DEBUG] Screenshot failed '{name}': {e}")


def save_html(page, name):
    try:
        with open(f"{DEBUG_DIR}/{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print(f"[DEBUG] HTML failed '{name}': {e}")


def dismiss_cookies(page):
    for label in ["ACCEPT ALL", "ACCEPT", "Accept All", "Accept"]:
        for tag in ["button", "span"]:
            try:
                el = page.locator(f"{tag}:has-text('{label}')").first
                if el.is_visible(timeout=500):
                    el.click()
                    page.wait_for_timeout(800)
                    print(f"[COOKIE] Dismissed with '{label}'")
                    return
            except:
                continue


def dismiss_popup(page):
    """Close any post-claim modal quickly."""
    # Milestone modal with CONTINUE button
    try:
        milestone = page.locator(".modal-bundle span.primary-button").first
        if milestone.is_visible(timeout=1000):
            milestone.click(force=True)
            page.wait_for_timeout(1000)
            print("[CLAIM]   Dismissed milestone modal.")
            return True
    except:
        pass

    # Purchase success modal — click backdrop corner
    try:
        success = page.locator(".purchase-handler.modal-backdrop").first
        if success.is_visible(timeout=800):
            success.click(position={"x": 10, "y": 10})
            page.wait_for_timeout(800)
            print("[CLAIM]   Dismissed success modal.")
            return True
    except:
        pass

    # Fallback
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except:
        pass
    return False


def wait_for_store_ready(page):
    """Wait for the store SPA to fully load after OAuth redirect."""
    print("[NAV] Waiting for store SPA to settle...")
    page.wait_for_url(
        re.compile(r"store\.playcontestofchampions\.com"),
        timeout=90000,
        wait_until="commit"
    )
    # Wait for the header as a signal the SPA is hydrated
    try:
        page.wait_for_selector("#header-bar", state="attached", timeout=20000)
    except PWTimeout:
        print("[NAV] Header not found, continuing anyway...")
    page.wait_for_timeout(1500)
    print(f"[NAV] Store ready at: {page.url}")


def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

    print("[LOGIN] Waiting for LOGIN button...")
    page.wait_for_selector("span.button-login", state="attached", timeout=30000)
    dismiss_cookies(page)
    save_debug(page, "01_store")

    print("[LOGIN] Clicking LOGIN button...")
    page.evaluate("document.querySelector('span.button-login').click()")

    print("[LOGIN] Waiting for kid.kabam.com...")
    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    save_debug(page, "02_kabam")

    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"]', state="visible", timeout=20000)
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    save_debug(page, "03_filled")

    print("[LOGIN] Submitting...")
    try:
        page.locator('button[type="submit"]').first.click()
    except:
        page.keyboard.press("Enter")

    wait_for_store_ready(page)
    dismiss_cookies(page)
    save_debug(page, "04_post_login")
    save_html(page, "04_post_login")


def get_claimable_buttons(page):
    """Return list of visible, non-login, non-sold-out FREE buttons."""
    claimable = []
    btns = page.locator(".item-action-free span.primary-button")
    for i in range(btns.count()):
        btn = btns.nth(i)
        try:
            txt = btn.inner_text(timeout=500).strip().upper()
            if "LOGIN" not in txt and "SOLD" not in txt and btn.is_visible(timeout=300):
                claimable.append(btn)
        except:
            continue
    return claimable


def claim_rewards(page):
    print("[CLAIM] Starting reward scan...")

    # Single fast scroll to trigger lazy-loaded items, then back to top
    page.evaluate("""
        () => new Promise(resolve => {
            const distance = 800;
            const steps = Math.ceil(document.body.scrollHeight / distance);
            let i = 0;
            const interval = setInterval(() => {
                window.scrollBy(0, distance);
                if (++i >= steps) {
                    clearInterval(interval);
                    window.scrollTo(0, 0);
                    resolve();
                }
            }, 100);
        })
    """)
    page.wait_for_timeout(1200)

    save_debug(page, "05_after_scroll")

    claimable = get_claimable_buttons(page)
    sold_out = page.locator(".item-action-free .item-sold-out").count()
    print(f"[CLAIM] Found {len(claimable)} claimable, {sold_out} sold out")

    if not claimable:
        print("[CLAIM] Nothing to claim.")
        send_telegram_msg(f"✅ Store checked — nothing to claim today ({sold_out} item(s) sold out/reset pending).")
        return

    claimed = 0
    consecutive_failures = 0
    max_failures = 3

    while True:
        claimable = get_claimable_buttons(page)
        if not claimable:
            print("[CLAIM] No more claimable items.")
            break

        btn = claimable[0]
        prev_count = len(claimable)

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            btn.click(force=True)

            # Wait for modal to appear rather than a fixed sleep
            try:
                page.wait_for_selector(
                    ".modal-backdrop, .purchase-handler",
                    state="visible",
                    timeout=4000
                )
            except PWTimeout:
                pass  # No modal is also fine

            dismiss_popup(page)

            new_claimable = get_claimable_buttons(page)
            if len(new_claimable) < prev_count:
                claimed += 1
                consecutive_failures = 0
                print(f"[CLAIM]   ✅ Claimed! Total: {claimed}, Remaining: {len(new_claimable)}")
            else:
                consecutive_failures += 1
                print(f"[CLAIM]   ⚠️ Count unchanged. Failure #{consecutive_failures}")
                save_debug(page, f"stuck_{consecutive_failures}")
                save_html(page, f"stuck_{consecutive_failures}")
                if consecutive_failures >= max_failures:
                    print("[CLAIM]   Too many failures — stopping.")
                    break

        except Exception as e:
            consecutive_failures += 1
            print(f"[CLAIM] Error: {e}")
            save_debug(page, f"error_{claimed}")
            if consecutive_failures >= max_failures:
                break

    # Final report
    remaining = get_claimable_buttons(page)
    sold_out = page.locator(".item-action-free .item-sold-out").count()

    if claimed > 0 and not remaining:
        msg = f"✅ Claimed all {claimed} free reward(s)!"
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"
    elif claimed > 0 and remaining:
        msg = f"⚠️ Claimed {claimed} but {len(remaining)} still unclaimed — check debug."
    else:
        msg = "👀 Nothing claimed today."
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"

    send_telegram_msg(msg)
    print(f"[CLAIM] Done. {msg}")


def run():
    print(f"EMAIL set: {'yes' if EMAIL else 'NO'}")

    if not EMAIL or not PASSWORD:
        print("Missing credentials!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--disable-default-apps",
                "--mute-audio",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Block images and fonts to speed up page loads
            java_script_enabled=True,
        )

        # Block unnecessary resources
        context.route(
            re.compile(r"\.(woff2?|ttf|otf|eot)(\?.*)?$"),
            lambda route: route.abort()
        )

        page = context.new_page()

        try:
            login(page)
            claim_rewards(page)

        except Exception as e:
            print(f"[RUN] FATAL ERROR: {e}")
            send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
            try:
                save_debug(page, "fatal_error")
                save_html(page, "fatal_error")
            except:
                pass
        finally:
            context.close()
            browser.close()
            print("[RUN] Done.")


if __name__ == "__main__":
    run()import os
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
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


def save_debug(page, name):
    try:
        page.screenshot(path=f"{DEBUG_DIR}/{name}.png", full_page=True)
    except Exception as e:
        print(f"[DEBUG] Screenshot failed '{name}': {e}")


def save_html(page, name):
    try:
        with open(f"{DEBUG_DIR}/{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print(f"[DEBUG] HTML failed '{name}': {e}")


def dismiss_cookies(page):
    for label in ["ACCEPT ALL", "ACCEPT", "Accept All", "Accept"]:
        for tag in ["button", "span"]:
            try:
                el = page.locator(f"{tag}:has-text('{label}')").first
                if el.is_visible(timeout=500):
                    el.click()
                    page.wait_for_timeout(800)
                    print(f"[COOKIE] Dismissed with '{label}'")
                    return
            except:
                continue


def dismiss_popup(page):
    """Close any post-claim modal quickly."""
    # Milestone modal with CONTINUE button
    try:
        milestone = page.locator(".modal-bundle span.primary-button").first
        if milestone.is_visible(timeout=1000):
            milestone.click(force=True)
            page.wait_for_timeout(1000)
            print("[CLAIM]   Dismissed milestone modal.")
            return True
    except:
        pass

    # Purchase success modal — click backdrop corner
    try:
        success = page.locator(".purchase-handler.modal-backdrop").first
        if success.is_visible(timeout=800):
            success.click(position={"x": 10, "y": 10})
            page.wait_for_timeout(800)
            print("[CLAIM]   Dismissed success modal.")
            return True
    except:
        pass

    # Fallback
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except:
        pass
    return False


def wait_for_store_ready(page):
    """Wait for the store SPA to fully load after OAuth redirect."""
    print("[NAV] Waiting for store SPA to settle...")
    page.wait_for_url(
        re.compile(r"store\.playcontestofchampions\.com"),
        timeout=90000,
        wait_until="commit"
    )
    # Wait for the header as a signal the SPA is hydrated
    try:
        page.wait_for_selector("#header-bar", state="attached", timeout=20000)
    except PWTimeout:
        print("[NAV] Header not found, continuing anyway...")
    page.wait_for_timeout(1500)
    print(f"[NAV] Store ready at: {page.url}")


def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

    print("[LOGIN] Waiting for LOGIN button...")
    page.wait_for_selector("span.button-login", state="attached", timeout=30000)
    dismiss_cookies(page)
    save_debug(page, "01_store")

    print("[LOGIN] Clicking LOGIN button...")
    page.evaluate("document.querySelector('span.button-login').click()")

    print("[LOGIN] Waiting for kid.kabam.com...")
    page.wait_for_url(re.compile(r"kid\.kabam\.com"), timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    save_debug(page, "02_kabam")

    print("[LOGIN] Filling credentials...")
    page.wait_for_selector('input[type="email"]', state="visible", timeout=20000)
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    save_debug(page, "03_filled")

    print("[LOGIN] Submitting...")
    try:
        page.locator('button[type="submit"]').first.click()
    except:
        page.keyboard.press("Enter")

    wait_for_store_ready(page)
    dismiss_cookies(page)
    save_debug(page, "04_post_login")
    save_html(page, "04_post_login")


def get_claimable_buttons(page):
    """Return list of visible, non-login, non-sold-out FREE buttons."""
    claimable = []
    btns = page.locator(".item-action-free span.primary-button")
    for i in range(btns.count()):
        btn = btns.nth(i)
        try:
            txt = btn.inner_text(timeout=500).strip().upper()
            if "LOGIN" not in txt and "SOLD" not in txt and btn.is_visible(timeout=300):
                claimable.append(btn)
        except:
            continue
    return claimable


def claim_rewards(page):
    print("[CLAIM] Starting reward scan...")

    # Single fast scroll to trigger lazy-loaded items, then back to top
    page.evaluate("""
        () => new Promise(resolve => {
            const distance = 800;
            const steps = Math.ceil(document.body.scrollHeight / distance);
            let i = 0;
            const interval = setInterval(() => {
                window.scrollBy(0, distance);
                if (++i >= steps) {
                    clearInterval(interval);
                    window.scrollTo(0, 0);
                    resolve();
                }
            }, 100);
        })
    """)
    page.wait_for_timeout(1200)

    save_debug(page, "05_after_scroll")

    claimable = get_claimable_buttons(page)
    sold_out = page.locator(".item-action-free .item-sold-out").count()
    print(f"[CLAIM] Found {len(claimable)} claimable, {sold_out} sold out")

    if not claimable:
        print("[CLAIM] Nothing to claim.")
        send_telegram_msg(f"✅ Store checked — nothing to claim today ({sold_out} item(s) sold out/reset pending).")
        return

    claimed = 0
    consecutive_failures = 0
    max_failures = 3

    while True:
        claimable = get_claimable_buttons(page)
        if not claimable:
            print("[CLAIM] No more claimable items.")
            break

        btn = claimable[0]
        prev_count = len(claimable)

        try:
            print(f"[CLAIM] Clicking item #{claimed + 1}...")
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            btn.click(force=True)

            # Wait for modal to appear rather than a fixed sleep
            try:
                page.wait_for_selector(
                    ".modal-backdrop, .purchase-handler",
                    state="visible",
                    timeout=4000
                )
            except PWTimeout:
                pass  # No modal is also fine

            dismiss_popup(page)

            new_claimable = get_claimable_buttons(page)
            if len(new_claimable) < prev_count:
                claimed += 1
                consecutive_failures = 0
                print(f"[CLAIM]   ✅ Claimed! Total: {claimed}, Remaining: {len(new_claimable)}")
            else:
                consecutive_failures += 1
                print(f"[CLAIM]   ⚠️ Count unchanged. Failure #{consecutive_failures}")
                save_debug(page, f"stuck_{consecutive_failures}")
                save_html(page, f"stuck_{consecutive_failures}")
                if consecutive_failures >= max_failures:
                    print("[CLAIM]   Too many failures — stopping.")
                    break

        except Exception as e:
            consecutive_failures += 1
            print(f"[CLAIM] Error: {e}")
            save_debug(page, f"error_{claimed}")
            if consecutive_failures >= max_failures:
                break

    # Final report
    remaining = get_claimable_buttons(page)
    sold_out = page.locator(".item-action-free .item-sold-out").count()

    if claimed > 0 and not remaining:
        msg = f"✅ Claimed all {claimed} free reward(s)!"
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"
    elif claimed > 0 and remaining:
        msg = f"⚠️ Claimed {claimed} but {len(remaining)} still unclaimed — check debug."
    else:
        msg = "👀 Nothing claimed today."
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"

    send_telegram_msg(msg)
    print(f"[CLAIM] Done. {msg}")


def run():
    print(f"EMAIL set: {'yes' if EMAIL else 'NO'}")

    if not EMAIL or not PASSWORD:
        print("Missing credentials!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--disable-default-apps",
                "--mute-audio",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Block images and fonts to speed up page loads
            java_script_enabled=True,
        )

        # Block unnecessary resources
        context.route(
            re.compile(r"\.(woff2?|ttf|otf|eot)(\?.*)?$"),
            lambda route: route.abort()
        )

        page = context.new_page()

        try:
            login(page)
            claim_rewards(page)

        except Exception as e:
            print(f"[RUN] FATAL ERROR: {e}")
            send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
            try:
                save_debug(page, "fatal_error")
                save_html(page, "fatal_error")
            except:
                pass
        finally:
            context.close()
            browser.close()
            print("[RUN] Done.")


if __name__ == "__main__":
    run()
