import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
STORE_URL = "https://store.playcontestofchampions.com/"
# לינק ישיר לעקיפת המודלים של האתר
XSOLLA_AUTH_URL = "https://login.xsolla.com/api/social/kabam/login_redirect?projectId=2c9de8c3-c57c-4bfe-83e6-20416f767517&login_url=https%3A%2F%2Fstore.playcontestofchampions.com&payload=%7B%7D&locale=en_US&trackId=&login_url=https%3A%2F%2Flogin-widget.xsolla.com%2Flatest%2Fsocial-auth-succeed%3FprojectId%3D2c9de8c3-c57c-4bfe-83e6-20416f767517%26callbackUrl%3Dhttps%3A%2F%2Fstore.playcontestofchampions.com"

def save_debug_info(page, name):
    """פונקציה לשמירת צילום מסך ו-HTML לדיבאג"""
    try:
        page.screenshot(path=f"./{name}.png")
        with open(f"./{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"DEBUG: Saved {name}.png and {name}.html")
    except Exception as e:
        print(f"DEBUG Error: Could not save debug info for {name}: {e}")

def login_and_save(browser):
    print("Starting fresh login via Xsolla...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        print("Navigating to Xsolla Auth Page...")
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        
        print("Filling credentials...")
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        
        save_debug_info(page, "1_login_page_filled")
        page.keyboard.press("Enter")

        print("Waiting for redirection back to store...")
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        
        # מחכים שהחנות תטען
        page.wait_for_selector("text=CART", timeout=40000)
        
        # שמירת המצב (Cookies/Session)
        context.storage_state(path=SESSION_FILE)
        print("SUCCESS: Session saved to JSON.")
        save_debug_info(page, "2_post_login_success")

    except Exception as e:
        print(f"ERROR: Login failed: {e}")
        save_debug_info(page, "error_login_step")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000) 

    # גלילה הדרגתית כדי להטעין את כל הפריטים
    for i in range(8):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

    # צילום מסך של החנות המלאה לפני האיסוף
    save_debug_info(page, "3_store_scanned_view")

    # חיפוש כפתורי איסוף (FREE/GET/CLAIM)
    selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM')"
    reward_buttons = page.locator(selector)
    count = reward_buttons.count()
    print(f"Found {count} potential reward buttons.")

    claimed = 0
    for i in range(count):
        try:
            btn = reward_buttons.nth(i)
            btn_text = btn.inner_text().strip()
            
            # דילוג על מוצרים בתשלום
            if "$" in btn_text or "MONTH" in btn_text:
                continue

            print(f"Attempting to claim reward {claimed + 1}: '{btn_text}'")
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            btn.click(force=True)
            
            # המתנה לפופ-אפ אישור
            page.wait_for_timeout(5000)
            save_debug_info(page, f"4_claim_{claimed+1}_result")
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
            claimed += 1
        except Exception as e:
            print(f"Could not claim item {i}: {e}")

    print(f"Finished claiming {claimed} items.")

def run():
    if not EMAIL or not PASSWORD:
        print("MISSING SECRETS: KABAM_EMAIL or KABAM_PASSWORD")
        return

    with sync_playwright() as p:
        # הפעלה במצב headless עבור GitHub Actions
        browser = p.chromium.launch(headless=True)
        
        # לוגין אם אין קובץ סשן שמור מה-Cache
        if not os.path.exists(SESSION_FILE):
            print("Session file not found. Starting login process...")
            login_and_save(browser)
        else:
            print("Session file found in cache. Using existing login.")

        # טעינת הדפדפן עם הסשן הקיים
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print(f"Opening store...")
            page.goto(STORE_URL, wait_until="networkidle")
            
            # צילום מסך מיידי - חייב להיווצר בכל הרצה
            save_debug_info(page, "0_landing_check")
            
            # בדיקה אם אנחנו עדיין מחוברים (אם אין עגלה, הסשן פג)
            if page.locator("text=CART").count() == 0:
                print("Session expired. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")

            claim_rewards(page)
            
        except Exception as e:
            print(f"RUNTIME ERROR: {e}")
            save_debug_info(page, "fatal_runtime_error")
        finally:
            browser.close()
            print("Done.")

if __name__ == "__main__":
    run()
