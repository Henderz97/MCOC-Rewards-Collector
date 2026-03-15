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
        # איתור כפתור הלוגין בראש העמוד
        login_header_btn = page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first
        
        # הגדרת הסלקטור לכפתור הכתום
        kabam_orange_btn = page.locator("button").filter(has_text=re.compile(r"LOGIN WITH KABAM", re.I))
        
        # לולאת לחיצות עד להופעת המודל
        for i in range(5):
            print(f"Click attempt {i+1} on top-right LOG IN...")
            login_header_btn.click(force=True)
            page.wait_for_timeout(3000)
            
            if kabam_orange_btn.is_visible():
                print("Modal is visible!")
                break
            
            # דיאגנוסטיקה: אם לא רואה את הכפתור, נדפיס מה הוא כן רואה
            if i == 4: # בניסיון האחרון
                all_buttons = page.locator("button").all_inner_texts()
                print(f"DEBUG: Found these buttons on page: {all_buttons}")

        if not kabam_orange_btn.is_visible():
            # ניסיון אחרון - אולי זה לינק ולא כפתור?
            kabam_alt = page.locator("text=LOGIN WITH KABAM")
            if kabam_alt.is_visible():
                print("Found as text/link, clicking...")
                kabam_orange_btn = kabam_alt
            else:
                raise Exception("Login modal never appeared.")

        print("Opening Kabam Auth window...")
        with context.expect_page() as new_page_info:
            kabam_orange_btn.click(force=True)
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        # שימוש ב-Selectors יציבים לפי placeholder או label
        try:
            auth_page.get_by_placeholder(re.compile("email", re.I)).fill(EMAIL)
            auth_page.get_by_placeholder(re.compile("password", re.I)).fill(PASSWORD)
        except:
            auth_page.locator('input[type="email"]').fill(EMAIL)
            auth_page.locator('input[type="password"]').fill(PASSWORD)
            
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
    # גלילה הדרגתית
    for _ in range(4):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
    # חיפוש כפתורי פרסים
    while claimed < 20:
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
            
            # המתנה לאישור
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1500)
            claimed += 1
        except Exception as e:
            print(f"Issue with reward: {e}. Refreshing...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(4000)
            
    print(f"Finished. Total claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Secrets KABAM_EMAIL or KABAM_PASSWORD are missing.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # שלב 1: לוגין ושמירת סשן
        login_and_save(browser)

        # שלב 2: ביצוע הפעולות עם הסשן
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
