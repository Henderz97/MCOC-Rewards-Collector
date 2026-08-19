import os
import re
import sys
import time
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

# How many times we retry a single stubborn item before moving on to the next one.
MAX_ATTEMPTS_PER_ITEM = 2
# Hard ceiling on total click attempts, so we can never spin forever.
MAX_TOTAL_ATTEMPTS = 30
# How long to wait for the store SPA to reflect a successful claim.
CLAIM_CONFIRM_TIMEOUT_MS = 9000


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
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Modal handling
# ---------------------------------------------------------------------------

MODAL_SELECTOR = ".modal-backdrop, .purchase-handler, .modal-bundle, .modal"

MODAL_OPEN_JS = """
(sel) => {
  const els = document.querySelectorAll(sel);
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.width > 1 && r.height > 1 &&
        s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') {
      return true;
    }
  }
  return false;
}
"""

NUKE_MODAL_JS = """
(sel) => {
  let n = 0;
  document.querySelectorAll(sel).forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 1 && r.height > 1) { el.remove(); n++; }
  });
  document.body.style.overflow = '';
  document.documentElement.style.overflow = '';
  document.body.classList.remove('modal-open', 'no-scroll', 'overflow-hidden');
  return n;
}
"""

# Close affordances, scoped inside a modal so we never click a store item by accident.
MODAL_CLOSE_SELECTORS = [
    ".modal-bundle span.primary-button",
    ".purchase-handler span.primary-button",
    ".modal-backdrop span.primary-button",
    ".modal .close, .modal-close, .modal [class*='close']",
    ".modal-backdrop [class*='close']",
    ".purchase-handler [class*='close']",
]


def modal_open(page):
    try:
        return bool(page.evaluate(MODAL_OPEN_JS, MODAL_SELECTOR))
    except Exception:
        return False


def close_modals(page, context=""):
    """Close whatever modal is on screen. Returns True if the screen ended up clear."""
    if not modal_open(page):
        return True

    for attempt in range(1, 5):
        # 1. Named close affordances inside the modal.
        for sel in MODAL_CLOSE_SELECTORS:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible(timeout=300):
                    el.click(force=True, timeout=2000)
                    page.wait_for_timeout(700)
                    if not modal_open(page):
                        print(f"[MODAL] Closed via '{sel}' (round {attempt})")
                        return True
            except Exception:
                continue

        # 2. Escape key.
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            if not modal_open(page):
                print(f"[MODAL] Closed via Escape (round {attempt})")
                return True
        except Exception:
            pass

        # 3. Click the backdrop away from the dialog body.
        try:
            backdrop = page.locator(".modal-backdrop, .purchase-handler").first
            if backdrop.count():
                backdrop.click(position={"x": 8, "y": 8}, force=True, timeout=2000)
                page.wait_for_timeout(600)
                if not modal_open(page):
                    print(f"[MODAL] Closed via backdrop click (round {attempt})")
                    return True
        except Exception:
            pass

    # 4. Last resort: rip it out of the DOM so it stops swallowing clicks.
    try:
        save_debug(page, f"modal_stuck_{context}")
        save_html(page, f"modal_stuck_{context}")
        removed = page.evaluate(NUKE_MODAL_JS, MODAL_SELECTOR)
        page.wait_for_timeout(400)
        print(f"[MODAL] ⚠️ Force-removed {removed} stuck modal element(s) ({context})")
    except Exception as e:
        print(f"[MODAL] Force-removal failed: {e}")

    return not modal_open(page)


# ---------------------------------------------------------------------------
# Item scanning
# ---------------------------------------------------------------------------

SCAN_JS = """
() => {
  const containers = Array.from(document.querySelectorAll('.item-action-free'));
  const seen = {};
  return containers.map((c, i) => {
    // Walk up a few levels to reach the item card, so the label is the item
    // name rather than the button caption.
    let card = c;
    for (let hop = 0; hop < 3 && card.parentElement; hop++) card = card.parentElement;
    let label = ((card.innerText || c.innerText || '')
                  .replace(/\\s+/g, ' ').trim().slice(0, 90)) || ('item-' + i);
    // Disambiguate items that share a label.
    seen[label] = (seen[label] || 0) + 1;
    const key = label + '##' + seen[label];

    if (!c.dataset.collectorId) {
      c.dataset.collectorId = 'mcoc-' + i + '-' + Math.random().toString(36).slice(2, 8);
    }

    const btn = c.querySelector('span.primary-button');
    const soldOut = !!c.querySelector('.item-sold-out');
    const txt = btn ? (btn.innerText || '').trim().toUpperCase() : '';
    let visible = false;
    if (btn) {
      const r = btn.getBoundingClientRect();
      const s = getComputedStyle(btn);
      visible = r.width > 1 && r.height > 1 &&
                s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
    }
    const claimable = !!btn && visible && !soldOut &&
                      !txt.includes('LOGIN') && !txt.includes('SOLD');
    return {id: c.dataset.collectorId, key, label, text: txt, claimable, soldOut};
  });
}
"""


def scan_items(page):
    try:
        return page.evaluate(SCAN_JS) or []
    except Exception as e:
        print(f"[SCAN] Failed: {e}")
        return []


def claimable_items(items):
    return [it for it in items if it.get("claimable")]


def full_scroll(page):
    """Scroll the page end to end to force lazy-loaded items into the DOM."""
    try:
        page.evaluate("""
            () => new Promise(resolve => {
                const distance = 800;
                const steps = Math.ceil(document.body.scrollHeight / distance) + 2;
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
    except Exception as e:
        print(f"[SCROLL] Failed: {e}")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def wait_for_store_ready(page):
    print("[NAV] Waiting for store SPA to settle...")
    page.wait_for_url(
        re.compile(r"store\.playcontestofchampions\.com"),
        timeout=90000,
        wait_until="commit"
    )
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
    except Exception:
        page.keyboard.press("Enter")

    wait_for_store_ready(page)
    dismiss_cookies(page)
    save_debug(page, "04_post_login")


# ---------------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------------

def click_item(page, item):
    """Click one item's FREE button. Returns True if a click was dispatched."""
    sel = f'[data-collector-id="{item["id"]}"] span.primary-button'
    btn = page.locator(sel).first

    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(250)
    except Exception:
        pass

    # Preferred: a real click with actionability checks, so an overlay makes this
    # fail loudly rather than silently landing on a backdrop.
    try:
        btn.click(timeout=5000)
        return True
    except Exception as e:
        print(f"[CLAIM]   Normal click blocked ({type(e).__name__}), trying JS dispatch...")

    # Fallback: dispatch straight to the element, bypassing any overlay.
    try:
        clicked = page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                el.click();
                return true;
            }""",
            sel,
        )
        if clicked:
            print("[CLAIM]   JS dispatch sent.")
            return True
        print("[CLAIM]   Element vanished before JS dispatch.")
    except Exception as e:
        print(f"[CLAIM]   JS dispatch failed: {e}")

    return False


def wait_for_claim_confirmed(page, key, timeout_ms=CLAIM_CONFIRM_TIMEOUT_MS):
    """Poll until THIS item stops being claimable. Per-item, not a global count."""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        items = scan_items(page)
        match = next((x for x in items if x["key"] == key), None)
        if match is None or not match["claimable"]:
            return True
        page.wait_for_timeout(600)
    return False


def claim_rewards(page):
    """Claim every free item. Returns (claimed, remaining_keys, sold_out)."""
    print("[CLAIM] Starting reward scan...")
    full_scroll(page)
    save_debug(page, "05_after_scroll")

    items = scan_items(page)
    pending = claimable_items(items)
    # Counted up front: items already unavailable when we arrived. Counting at the
    # end would fold in everything we just claimed, which reads as a false alarm.
    sold_out = sum(1 for it in items if it["soldOut"])
    print(f"[CLAIM] Found {len(pending)} claimable, {sold_out} sold out")
    for it in pending:
        print(f"[CLAIM]   • {it['label']} [{it['text']}]")

    if not pending:
        return 0, [], sold_out

    attempts = {}          # key -> attempts made
    claimed = 0
    total_attempts = 0

    while total_attempts < MAX_TOTAL_ATTEMPTS:
        items = scan_items(page)
        pending = claimable_items(items)
        if not pending:
            print("[CLAIM] No more claimable items.")
            break

        # Pick the first item that still has attempts left. This is the key fix:
        # a stuck item is skipped instead of blocking everything behind it.
        target = next(
            (it for it in pending if attempts.get(it["key"], 0) < MAX_ATTEMPTS_PER_ITEM),
            None,
        )
        if target is None:
            print(f"[CLAIM] {len(pending)} item(s) exhausted their retries — giving up on them.")
            break

        key = target["key"]
        attempts[key] = attempts.get(key, 0) + 1
        total_attempts += 1
        attempt_no = attempts[key]
        print(f"[CLAIM] → '{target['label']}' (attempt {attempt_no}/{MAX_ATTEMPTS_PER_ITEM})")

        # Never click with a modal still up — that is how clicks got eaten before.
        close_modals(page, context=f"before_{total_attempts}")

        dispatched = click_item(page, target)
        if not dispatched:
            save_debug(page, f"stuck_{total_attempts}")
            save_html(page, f"stuck_{total_attempts}")
            continue

        # Let the confirmation modal appear, then clear it.
        try:
            page.wait_for_selector(MODAL_SELECTOR, state="visible", timeout=4000)
        except PWTimeout:
            pass
        close_modals(page, context=f"after_{total_attempts}")

        if wait_for_claim_confirmed(page, key):
            claimed += 1
            print(f"[CLAIM]   ✅ Claimed '{target['label']}'. Total: {claimed}")
        else:
            print(f"[CLAIM]   ⚠️ '{target['label']}' still claimable after {CLAIM_CONFIRM_TIMEOUT_MS}ms")
            save_debug(page, f"stuck_{total_attempts}")
            save_html(page, f"stuck_{total_attempts}")

    if total_attempts >= MAX_TOTAL_ATTEMPTS:
        print("[CLAIM] Hit the total attempt ceiling — stopping.")

    # Final state: rescan from scratch, including a fresh scroll in case new rows
    # lazy-loaded while we were working.
    full_scroll(page)
    items = scan_items(page)
    remaining = [it["label"] for it in claimable_items(items)]
    save_debug(page, "06_final")
    if remaining:
        save_html(page, "06_final")

    return claimed, remaining, sold_out


def report(claimed, remaining, sold_out):
    if claimed > 0 and not remaining:
        msg = f"✅ Claimed all {claimed} free reward(s)!"
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"
    elif claimed > 0 and remaining:
        msg = (f"⚠️ Claimed {claimed}, but {len(remaining)} still unclaimed: "
               f"{', '.join(remaining[:3])} — see the debug artifact.")
    elif not claimed and remaining:
        msg = (f"❌ Claimed nothing — {len(remaining)} item(s) available but unclaimable: "
               f"{', '.join(remaining[:3])} — see the debug artifact.")
    else:
        msg = "✅ Store checked — nothing to claim today."
        if sold_out:
            msg += f" ({sold_out} item(s) sold out — will reset later)"

    send_telegram_msg(msg)
    print(f"[CLAIM] Done. {msg}")


def run():
    print(f"EMAIL set: {'yes' if EMAIL else 'NO'}")

    if not EMAIL or not PASSWORD:
        print("Missing credentials!")
        send_telegram_msg("⚠️ Missing credentials — check repository secrets.")
        sys.exit(1)

    remaining = []

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
            java_script_enabled=True,
        )

        context.route(
            re.compile(r"\.(woff2?|ttf|otf|eot)(\?.*)?$"),
            lambda route: route.abort()
        )

        page = context.new_page()

        try:
            login(page)
            claimed, remaining, sold_out = claim_rewards(page)
            report(claimed, remaining, sold_out)

        except Exception as e:
            print(f"[RUN] FATAL ERROR: {e}")
            send_telegram_msg(f"⚠️ Fatal error: {str(e)[:200]}")
            try:
                save_debug(page, "fatal_error")
                save_html(page, "fatal_error")
            except Exception:
                pass
            raise

        finally:
            try:
                context.close()
            except Exception as e:
                print(f"[RUN] Context close failed: {e}")
            try:
                browser.close()
            except Exception as e:
                print(f"[RUN] Browser close failed: {e}")
            print("[RUN] Done.")

    # Fail the workflow when anything was left behind, so the run goes red and the
    # debug artifact is worth looking at.
    if remaining:
        print(f"[RUN] Exiting non-zero: {len(remaining)} item(s) left unclaimed.")
        sys.exit(1)


if __name__ == "__main__":
    run()
