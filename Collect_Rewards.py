import os
import re
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True
# ---------------------

STORE_URL = "https://store.playcontestofchampions.com/"

def login_and_save(browser):

    print("Starting fresh login...")

    context = browser.new_context(viewport={"width":1280,"height":720})
    page = context.new_page()

    try:

        print("Opening store page...")
        page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

        # Accept cookies
        try:
            print("Accepting cookies...")
            page.locator("text=ACCEPT ALL").click(timeout=5000)
        except:
            pass

        print("Clicking LOG IN...")
        page.locator("text=LOG IN").first.click()

        print("Waiting for login modal...")
        page.wait_for_timeout(4000)

        print("Locating Kabam button...")

        login_button = page.locator("button:has-text('KABAM'), a:has-text('KABAM')").first

        login_button.wait_for(timeout=30000)

        print("Opening Kabam login window...")

        with context.expect_page() as new_page_info:
            login_button.click(force=True)

        auth_page = new_page_info.value
        auth_page.wait_for_load_state("domcontentloaded")

        print("Entering credentials...")

        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)

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

    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
    page.wait_for_timeout(2000)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)

    page.screenshot(path="store_view.png")

    claimed = 0

    while claimed < 20:

        buttons = page.locator("button:has-text('GET FREE'), button:has-text('CLAIM')")

        if buttons.count() == 0:
            print("No claimable rewards found.")
            break

        print(f"Attempting to claim reward #{claimed+1}")

        try:

            btn = buttons.first
            btn.scroll_into_view_if_needed()

            page.wait_for_timeout(1000)

            btn.click(force=True)

            page.wait_for_timeout(5000)

            page.keyboard.press("Escape")

            page.wait_for_timeout(2000)

            claimed += 1

        except Exception as e:

            print(f"Claim failed: {e}, refreshing...")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

    print(f"Finished. Claimed {claimed} rewards.")


def run():

    if not EMAIL or not PASSWORD:
        print("Missing KABAM_EMAIL or KABAM_PASSWORD secrets.")
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=HEADLESS)

        login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:

            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

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
