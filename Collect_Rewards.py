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

        # סגירת הודעת קוקיז אם היא מפריעה
        try:
            page.locator("button:has-text('ACCEPT')").click(timeout=5000)
        except:
            pass

        # אסטרטגיה: לחיצה חוזרת על כפתור הלוגין בפינה עד שהמודל מופיע
        print("Attempting to trigger login modal...")
        login_header_btn = page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first
        
        # כפתור הכתום הספציפי מהתמונה שלך (לפי ה-Data Type שהאתר בדרך כלל משתמש בו)
        kabam_orange_btn = page.locator("button").filter(has_text=re.compile(r"LOGIN WITH KABAM", re.I))
        
        for i in range(5):
            print(f"Click attempt {i+1} on top-right LOG IN...")
            login_header_btn.click(force=True)
            page.wait_for_timeout(3000)
            if kabam_orange_btn.is_visible():
                print("Modal is visible!")
                break
        
        if not kabam_orange_btn.is_visible():
            raise Exception("Login modal never appeared even after multiple clicks.")

        print("Opening Kabam Auth window...")
        with context.expect_page() as new_page_info:
            kabam_orange_btn.click(force=True)
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        # שימוש ב-Selectors יותר יציבים לשדות
        auth_page.get_by_placeholder(re.compile("email", re.I)).fill(EMAIL)
        auth_page.get_by_placeholder(re.compile("password", re.I)).fill(PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for redirect back to store...")
        # נחכה ל-CART שמעיד שהסשן נטען
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
    # גלילה הדרגתית כדי להטעין הכל
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(1000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
    while claimed < 20:
        # איתור כפתורים
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
            
            # המתנה וסגירה
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1500)
            claimed += 1
        except:
            print("Issue with button, refreshing...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(4000)
            
    print(f"Process ended. Claimed {claimed} items.")

def run():
    if not EMAIL or not PASSWORD:
        print("Secrets missing.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # שלב 1: לוגין
        login_and_save(browser)

        # שלב 2: ביצוע פעולות
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            page.goto(STORE_URL, wait_until="networkidle")
            claim_rewards(page)
            page.screenshot(path="final_status.png")
        except Exception as e:
            print(f"Runtime error: {e}")
            page.screenshot(path="runtime_error.png")
        finally:
            print("Process complete.")
            browser.close()

if __name__ == "__main__":
    run()
