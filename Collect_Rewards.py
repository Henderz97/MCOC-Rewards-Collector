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
        page.goto(STORE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)

        # קוקיז
        try:
            page.get_by_role("button", name=re.compile("ACCEPT", re.I)).click(timeout=5000)
        except:
            pass

        print("Attempting to trigger login modal...")
        login_header_btn = page.locator("button").filter(has_text=re.compile(r"LOG IN", re.I)).first
        
        # סלקטורים אפשריים לכפתור הכתום
        kabam_btn_selector = "button.user-id-modal__button, button.simple-button--with-shadow"
        
        for i in range(5):
            print(f"Click attempt {i+1} on top-right LOG IN...")
            login_header_btn.click(force=True)
            page.wait_for_timeout(4000)
            
            # בדיקת נראות
            target = page.locator(kabam_btn_selector).first
            if target.count() > 0:
                is_visible = target.is_visible()
                print(f"DEBUG: Kabam button exists in DOM. Visible: {is_visible}")
                if is_visible:
                    break
            
            if i == 4:
                print("DEBUG: Final attempt failed. Printing buttons and modal HTML...")
                print(f"Visible buttons: {page.locator('button:visible').all_inner_texts()}")
                # הדפסת ה-HTML של המודל לדיבאג עמוק
                modal_html = page.evaluate("() => document.querySelector('.user-id-modal, [class*=\"modal\"]')?.outerHTML")
                print(f"MODAL HTML: {modal_html}")

        print("Opening Kabam Auth window...")
        # נסיון לחיצה משולב: קודם רגיל, אם נכשל אז JS
        try:
            with context.expect_page(timeout=15000) as new_page_info:
                # שימוש ב-JS ללחיצה כדי לעקוף "Not Visible"
                page.evaluate(f'document.querySelector("{kabam_btn_selector}").click()')
        except Exception as e:
            print(f"Standard popup trigger failed, trying emergency JS click: {e}")
            with context.expect_page() as new_page_info:
                page.evaluate('document.querySelectorAll("button").forEach(b => b.innerText.includes("KABAM") && b.click())')

        auth_page = new_page_info.value
        auth_page.wait_for_load_state("networkidle")

        print("Entering credentials...")
        auth_page.locator('input[type="email"]').fill(EMAIL)
        auth_page.locator('input[type="password"]').fill(PASSWORD)
        auth_page.keyboard.press("Enter")

        print("Waiting for redirect back to store...")
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
    for _ in range(6):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(1000)
    
    page.screenshot(path="store_view.png")
    
    claimed = 0
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
            page.wait_for_timeout(5000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            claimed += 1
        except:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
    print(f"Finished. Total: {claimed}")

def run():
    if not EMAIL or not PASSWORD:
        print("Secrets missing.")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        login_and_save(browser)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        try:
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=90000)
            claim_rewards(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
