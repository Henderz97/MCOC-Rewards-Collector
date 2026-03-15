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
        print("Opening store page (waiting for DOM)...")
        # שימוש ב-domcontentloaded במקום networkidle כדי למנוע Timeouts
        page.goto(STORE_URL, wait_until="domcontentloaded", timeout=90000)
        
        # השהיה קצרה לוודא שהאלמנטים הבסיסיים מרונדרים
        page.wait_for_timeout(5000)

        # סגירת קוקיז
        try:
            print("Checking for cookies...")
            page.get_by_role("button", name=re.compile("ACCEPT", re.I)).click(timeout=5000)
        except:
            pass

        print("Attempting to trigger login modal...")
        # נסיון לחיצה על כפתור הלוגין בראש העמוד
        login_header_btn = page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first
        
        # זיהוי הכפתור הכתום לפי ה-Class שראינו ב-Debug הקודם
        kabam_btn_selector = "button.user-id-modal__button, button.simple-button--with-shadow"
        
        for i in range(5):
            print(f"Click attempt {i+1} on top-right LOG IN...")
            login_header_btn.click(force=True)
            page.wait_for_timeout(4000)
            
            potential_btn = page.locator(kabam_btn_selector).first
            if potential_btn.is_visible():
                print("Modal button found!")
                break

        print("Opening Kabam Auth window...")
        with context.expect_page() as new_page_info:
            # לחיצה על הכפתור הכתום שמופיע במודל
            page.locator(kabam_btn_selector).first.click(force=True)
        
        auth_page = new_page_info.value
        # בדף האימות אנחנו מחכים לטעינה מלאה
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        # מילוי פרטים
        auth_page.locator('input[type="email"]').fill(EMAIL)
        auth_page.locator('input[type="password"]').fill(PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for redirect back to store...")
        # נחכה שהחנות תטען חזרה
        page.wait_for_selector("text=CART", timeout=90000)
        
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
    for _ in range(6):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(1000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
    while claimed < 20:
        # מחפשים כפתורי FREE או CLAIM
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
            
            # המתנה לאנימציית הצלחה
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except Exception:
            print("Error clicking reward, refreshing...")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
    print(f"Finished. Total claimed: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Secrets missing.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        
        # התחברות
        login_and_save(browser)

        # טעינת סשן וביצוע הפעולות
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            # גם כאן נשתמש ב-domcontentloaded
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=90000)
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
