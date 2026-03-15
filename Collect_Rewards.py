import os
import re
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

        # סגירת קוקיז אם קיימים
        try:
            print("Checking for cookies...")
            page.get_by_role("button", name=re.compile("ACCEPT", re.I)).click(timeout=5000)
        except:
            pass

        print("Clicking top-right LOG IN button...")
        # לחיצה על הכפתור בפינה הימנית העליונה
        page.get_by_role("button", name=re.compile("LOG IN", re.I)).first.click()

        print("Waiting for login modal to appear...")
        # נחכה שהכפתור הכתום מהתמונה שלך יופיע באמת ב-DOM
        kabam_btn = page.locator("button").filter(has_text=re.compile("LOGIN WITH KABAM", re.I))
        kabam_btn.wait_for(state="visible", timeout=15000)
        
        # השהייה קלה כדי לוודא שהאנימציה הסתיימה
        page.wait_for_timeout(2000)

        print("Clicking LOGIN WITH KABAM and waiting for popup...")
        with context.expect_page() as new_page_info:
            # לחיצה עם force=True למקרה שיש Overlay סמוי
            kabam_btn.click(force=True)
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for redirect back to store...")
        # מחכים שהחנות תיטען מחדש ותזהה אותנו (לפי הופעת ה-CART)
        page.wait_for_selector("text=CART", timeout=60000)
        
        context.storage_state(path=SESSION_FILE)
        print("Login successful and session saved.")

    except Exception as e:
        print(f"Login failed: {e}")
        page.screenshot(path="login_error.png")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    # גלילה מטה כדי להטעין את כל החנות
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
    # ננסה למצוא כפתורי GET FREE או CLAIM
    while claimed < 20:
        buttons = page.locator("button:has-text('GET FREE'), button:has-text('CLAIM')")
        
        if buttons.count() == 0:
            print("No more claimable rewards found.")
            break

        try:
            print(f"Claiming reward #{claimed + 1}...")
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            btn.click(force=True)
            
            # המתנה לאנימציית הצלחה וסגירת המודל עם Escape
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception as e:
            print(f"Error claiming item: {e}. Refreshing...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(5000)
            
    print(f"Finished. Total rewards claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Missing KABAM_EMAIL or KABAM_PASSWORD secrets.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # שלב 1: התחברות
        login_and_save(browser)

        # שלב 2: שימוש בסשן שנשמר כדי לאסוף פרסים
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
