import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
STORE_URL = "https://store.playcontestofchampions.com/"
HEADLESS = True 

def login_and_save(browser):
    print("Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    try:
        print("Opening store page...")
        page.goto(STORE_URL, wait_until="networkidle", timeout=60000)

        # סגירת קוקיז
        try:
            page.get_by_role("button", name=re.compile("ACCEPT", re.I)).click(timeout=5000)
        except:
            pass

        print("Attempting to trigger login modal...")
        login_header_btn = page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first
        
        # אסטרטגיה חדשה: חיפוש הכפתור לפי ה-Attribute שלו. 
        # לפי ה-DEBUG שלך, זה כנראה כפתור עם Class או סוג מסוים שנמצא בתוך ה-modal.
        kabam_btn_selector = "button.user-id-modal__button, button:has-text('Log in'), button:has(img)"
        
        for i in range(5):
            print(f"Click attempt {i+1} on top-right LOG IN...")
            login_header_btn.click(force=True)
            page.wait_for_timeout(3000)
            
            # בדיקה אם אחד מהכפתורים במודל מופיע
            potential_btn = page.locator(kabam_btn_selector).last
            if potential_btn.is_visible():
                print("Found potential Kabam login button!")
                kabam_orange_btn = potential_btn
                break
            
            if i == 4:
                print(f"DEBUG: Visible buttons during failure: {page.locator('button:visible').all_inner_texts()}")

        # לחיצה ופתיחת חלון האימות
        print("Opening Kabam Auth window...")
        with context.expect_page() as new_page_info:
            # אנחנו לוחצים על הכפתור האחרון במודל, שבדרך כלל הוא הכפתור הכתום
            page.locator("button.simple-button--with-shadow").click(force=True)
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        # נסיון מילוי גמיש
        auth_page.wait_for_selector('input[type="email"]', timeout=20000)
        auth_page.locator('input[type="email"]').fill(EMAIL)
        auth_page.locator('input[type="password"]').fill(PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for redirect back to store...")
        page.wait_for_selector("text=CART", timeout=60000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login successful.")

    except Exception as e:
        print(f"Login failed: {e}")
        page.screenshot(path="login_error.png")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    # גלילה עמוקה יותר
    for _ in range(5):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
    while claimed < 20:
        # איתור כפתורים עם טקסט חופשי
        buttons = page.locator("button").filter(has_text=re.compile(r"GET FREE|CLAIM", re.I))
        
        if buttons.count() == 0:
            print("No more claimable rewards.")
            break

        try:
            print(f"Claiming reward #{claimed + 1}...")
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            btn.click(force=True)
            
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
            print(f"Successfully claimed #{claimed}")
        except Exception as e:
            print(f"Click failed: {e}. Refreshing page...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(5000)
            
    print(f"Finished. Total items: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Missing credentials.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # שלב 1: לוגין
        login_and_save(browser)

        # שלב 2: סריקה
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto(STORE_URL, wait_until="networkidle")
            claim_rewards(page)
            page.screenshot(path="final_status.png")
        except Exception as e:
            print(f"Error during claim: {e}")
            page.screenshot(path="runtime_error.png")
        finally:
            print("Process complete.")
            browser.close()

if __name__ == "__main__":
    run()
