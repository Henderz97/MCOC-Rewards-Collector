import os
import re
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD") # Ensure this is correct
SESSION_FILE = "kabam_session.json"
HEADLESS = True  # Set to True to run invisibly in the background or False
# ---------------------

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        # Always login (GitHub runners are temporary)
        login_and_save(browser)

        if os.path.exists(SESSION_FILE):
            context = browser.new_context(storage_state=SESSION_FILE)
        else:
            context = browser.new_context()

        page = context.new_page()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Double-check if we are logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible(timeout=5000):
                print("Session expired. Performing fresh login...")
                context.close()

                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)

                login_and_save(browser)

                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto("https://store.playcontestofchampions.com/")

            claim_rewards(page)

        except Exception as e:
            print(f"Runtime error: {e}")

        finally:
            print("Process complete.")
            browser.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    time.sleep(5) # Allow store items to load
    
    claimed = 0
    # Specifically target 'GET FREE' to avoid 'OWNED' items
    while claimed < 20:
        buttons = page.get_by_role("button", name=re.compile("get free", re.I))
        
        if buttons.count() == 0:
            break

        print(f"Claiming reward #{claimed + 1}...")
        try:
            btn = buttons.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            
            # Dismiss the success modal
            time.sleep(4)
            page.keyboard.press("Escape")
            time.sleep(2)
            claimed += 1
        except:
            print("Action blocked, refreshing page...")
            page.reload()
            time.sleep(5)
            
    print(f"Finished! Total items claimed: {claimed}")

def run():
    with sync_playwright() as p:
        # Toggle HEADLESS here for background running
        browser = p.chromium.launch(headless=HEADLESS)

        # Initial login if no session file exists
        login_and_save(browser)
context = browser.new_context(storage_state=SESSION_FILE)
else:
    context = browser.new_context()

        try:
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            # Double-check if we are logged in
            if page.get_by_role("button", name=re.compile("log in", re.I)).is_visible(timeout=5000):
                print("Session expired. Performing fresh login...")
                context.close()
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                login_and_save(browser)
                # Re-open with new session
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto("https://store.playcontestofchampions.com/")

            claim_rewards(page)
        except Exception as e:
            print(f"Runtime error: {e}")
        finally:
            print("Process complete.")
            browser.close()

if __name__ == "__main__":
    run()




