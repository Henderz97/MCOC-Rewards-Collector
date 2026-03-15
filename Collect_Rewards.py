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
        page.goto(STORE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)

        # לחיצה על כפתור הלוגין הראשי בפינה
        print("Triggering login modal...")
        page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first.click(force=True)
        page.wait_for_timeout(3000)

        print("Executing force-click on Kabam login via JS...")
        # ה-JS הזה עושה 3 פעולות: 
        # 1. מוצא את הכפתור הכתום מה-HTML שלך.
        # 2. מוודא שהמודל לא מוסתר (hidden).
        # 3. לוחץ עליו כדי לפתוח את חלון הסיסמה.
        with context.expect_page() as new_page_info:
            page.evaluate("""() => {
                const btn = document.querySelector('button[data-type="user-id-button-continue"]');
                const container = document.querySelector('.user-id-modal__container');
                if(container) container.removeAttribute('hidden');
                if(btn) btn.click();
            }""")
        
        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        auth_page.locator('input[type="email"]').fill(EMAIL)
        auth_page.locator('input[type="password"]').fill(PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for store to reload with session...")
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
    # גלילה איטית
    for _ in range(6):
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(1000)
    
    claimed = 0
    while claimed < 20:
        # איתור כפתורי GET FREE או CLAIM
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
            page.keyboard.press("Escape") # סגירת הפופ-אפ של ה-Success
            page.wait_for_timeout(2000)
            claimed += 1
        except:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
    print(f"Finished! Claimed {claimed} items.")

def run():
    if not EMAIL or not PASSWORD:
        print("Missing secrets.")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        login_and_save(browser)
        
        # הרצה שניה עם הסשן השמור
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        try:
            page.goto(STORE_URL, wait_until="domcontentloaded")
            claim_rewards(page)
        finally:
            browser.close()

if __name__ == "__main__":
    run()
