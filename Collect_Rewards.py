import os
import re
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
STORE_URL = "https://store.playcontestofchampions.com/"
# הלינק הישיר שסיפקת ל-Xsolla
XSOLLA_AUTH_URL = "https://login.xsolla.com/api/social/kabam/login_redirect?projectId=2c9de8c3-c57c-4bfe-83e6-20416f767517&login_url=https%3A%2F%2Fstore.playcontestofchampions.com&payload=%7B%7D&locale=en_US&trackId=&login_url=https%3A%2F%2Flogin-widget.xsolla.com%2Flatest%2Fsocial-auth-succeed%3FprojectId%3D2c9de8c3-c57c-4bfe-83e6-20416f767517%26callbackUrl%3Dhttps%3A%2F%2Fstore.playcontestofchampions.com"

def login_and_save(browser):
    print("Starting direct Xsolla login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    try:
        # ניווט ישיר לדף הזנת הפרטים
        print("Navigating to Xsolla login page...")
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        
        print("Filling credentials...")
        # נחכה לשדות האימייל והסיסמה של Kabam בתוך דף ה-Xsolla
        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        
        print("Submitting...")
        # לחיצה על כפתור ה-Log In בדף של Xsolla
        # בדרך כלל יש שם כפתור מסוג submit או עם טקסט Log In
        page.keyboard.press("Enter")

        print("Waiting for redirection back to store...")
        # מחכים שהדף יחזור לכתובת של החנות
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        
        # אישור סופי שהגענו והסשן נטען
        page.wait_for_selector("text=CART", timeout=30000)
        
        # שמירת הסשן
        context.storage_state(path=SESSION_FILE)
        print("Login successful! Session saved.")

    except Exception as e:
        print(f"Login failed: {e}")
        page.screenshot(path="login_error.png")
        # הדפסת ה-URL הנוכחי כדי לראות איפה נתקענו
        print(f"Stuck at URL: {page.url}")
        raise e
    finally:
        context.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    # גלילה אגרסיבית להטענת כל הדף
    for _ in range(8):
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(800)
    
    # מציאת כל כפתורי ה-Claim
    buttons = page.locator("button").filter(has_text=re.compile(r"GET FREE|CLAIM", re.I))
    count = buttons.count()
    print(f"Found {count} buttons.")

    claimed = 0
    for i in range(count):
        try:
            btn = buttons.nth(i)
            # בדיקה שהכפתור באמת זמין ולא מוסתר
            if btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click(force=True)
                print(f"Claimed item {claimed + 1}")
                page.wait_for_timeout(3000)
                page.keyboard.press("Escape") # סגירת הודעת הצלחה
                claimed += 1
        except:
            continue
    print(f"Finished claiming {claimed} items.")

def run():
    if not EMAIL or not PASSWORD:
        print("Secrets missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # שלב 1: לוגין ושמירת קוקיז
        login_and_save(browser)
        
        # שלב 2: הרצה עם הקוקיז השמורים
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        page.goto(STORE_URL, wait_until="domcontentloaded")
        claim_rewards(page)
        
        browser.close()

if __name__ == "__main__":
    run()
