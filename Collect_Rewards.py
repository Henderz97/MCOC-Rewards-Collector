import os
import time
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

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 MCOC: {message}"}, timeout=15)
    except: pass

def save_debug(page, name):
    page.screenshot(path=f"{DEBUG_DIR}/{name}.png", full_page=True)

def login(page):
    print("[LOGIN] Navigating to store...")
    page.goto(STORE_URL, wait_until="networkidle")
    time.sleep(5)
    
    # Check if logged in based on your HTML structure
    if page.locator(".user-profile-dropdown").is_visible():
        print(f"[LOGIN] Already logged in as: {page.locator('.user-profile-dropdown .CTA').text_content()}")
        return

    print("[LOGIN] Not logged in. Starting flow...")
    page.get_by_text("LOGIN", exact=True).first.click()
    page.wait_for_selector('input[type="email"]')
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(STORE_URL, timeout=60000)
    time.sleep(5)

def claim_free_items(page):
    print("[CLAIM] Scanning for 'FREE' buttons...")
    
    # Scroll slowly to ensure all "FREE" buttons are rendered in the DOM
    for i in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    # Selector based on your HTML: span.CTA containing the word "FREE"
    free_selector = "span.CTA:has-text('FREE')"
    
    claimed_count = 0
    
    while True:
        # Refresh targets to avoid stale element errors
        targets = page.locator(free_selector)
        count = targets.count()
        
        if count == 0:
            print("[CLAIM] No more 'FREE' buttons found.")
            break

        # Always try to click the first visible/enabled one
        found_clickable = False
        for i in range(count):
            btn = targets.nth(i)
            if btn.is_visible() and btn.is_enabled():
                try:
                    btn.scroll_into_view_if_needed()
                    print(f"[CLAIM] Clicking FREE item #{claimed_count + 1}...")
                    btn.click(force=True)
                    
                    # Wait for the "Success" or "Item Details" modal
                    time.sleep(5)
                    save_debug(page, f"claim_success_{claimed_count + 1}")
                    
                    # Close modal if it appeared (usually 'Escape' or clicking backdrop)
                    page.keyboard.press("Escape")
                    time.sleep(2)
                    
                    claimed_count += 1
                    found_clickable = True
                    break # Re-scan the page after a successful click
                except Exception as e:
                    print(f"[CLAIM] Click error: {e}")
                    continue
        
        if not found_clickable:
            break

    msg = f"Successfully claimed {claimed_count} FREE items!" if claimed_count > 0 else "No FREE items were available to claim."
    send_telegram_msg(msg)
    print(f"[RUN] {msg}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            login(page)
            save_debug(page, "0_logged_in_state")
            claim_free_items(page)
        except Exception as e:
            print(f"[FATAL] {e}")
            save_debug(page, "ERROR_crash")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
