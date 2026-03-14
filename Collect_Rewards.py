import os
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError

# --- CONFIGURATION ---
EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"
HEADLESS = True
# ---------------------


def login_and_save(browser):
    print("Starting login process...")

    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    try:
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

        # Accept cookies
        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=5000)
        except:
            pass

        print("Clicking LOG IN button...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()

        page.wait_for_timeout(3000)

        print("Opening Kabam login popup...")

        with context.expect_page() as new_page_info:
            page.locator("button:has-text('Log In')").last.click()

        auth_page = new_page_info.value
        auth_page.wait_for_load_state()

        print("Filling credentials...")

        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)

        auth_page.keyboard.press("Enter")

        page.wait_for_selector("button:has-text('CART')", timeout=60000)

        context.storage_state(path=SESSION_FILE)

        print("Login successful. Session saved.")

    except Exception as e:
        print(f"Login failed: {e}")
        page.screenshot(path="login_error.png")
        raise e

    finally:
        context.close()


def claim_rewards(page):
    print("Scanning for rewards...")

    page.wait_for_timeout(5000)

    claimed = 0

    while claimed < 20:

        buttons = page.get_by_role("button", name=re.compile("get free|claim", re.I))

        if buttons.count() == 0:
            print("No more rewards found.")
            break

        try:
            btn = buttons.first

            print(f"Claiming reward #{claimed + 1}")

            btn.scroll_into_view_if_needed()
            btn.click(force=True)

            page.wait_for_timeout(4000)

            page.keyboard.press("Escape")

            page.wait_for_timeout(2000)

            claimed += 1

        except Exception as e:
            print(f"Claim error: {e}")

            page.screenshot(path=f"claim_error_{claimed}.png")

            page.reload()

            page.wait_for_timeout(5000)

    print(f"Finished. Total claimed: {claimed}")


def is_logged_in(page):
    try:
        return page.get_by_role("button", name=re.compile("cart", re.I)).is_visible(timeout=5000)
    except TimeoutError:
        return False


def run():

    if not EMAIL or not PASSWORD:
        print("KABAM_EMAIL or KABAM_PASSWORD missing.")
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=HEADLESS)

        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:

            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            if not is_logged_in(page):
                print("Session expired. Logging in again.")

                login_and_save(browser)

                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()

                page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")

            claim_rewards(page)

        except Exception as e:

            print(f"Runtime error: {e}")

            page.screenshot(path="runtime_error.png")

        finally:

            browser.close()

            print("Process complete.")


if __name__ == "__main__":
    run()
