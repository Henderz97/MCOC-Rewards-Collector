import os
import re
import time
from playwright.sync_api import sync_playwright

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

SESSION_FILE = "kabam_session.json"
HEADLESS = True


def login_and_save(browser):
    print("Starting login process...")

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=user_agent,
        locale="en-US"
    )

    page = context.new_page()

    try:
        page.goto(
            "https://store.playcontestofchampions.com/",
            wait_until="domcontentloaded",
            timeout=60000
        )

        time.sleep(5)

        try:
            page.get_by_role("button", name=re.compile("accept", re.I)).click(timeout=4000)
        except:
            pass

        print("Opening login modal...")
        page.get_by_role("button", name=re.compile("log in", re.I)).click()

        time.sleep(4)

        print("Clicking LOGIN WITH KABAM...")
        page.get_by_text("LOGIN WITH KABAM").click(force=True)

        time.sleep(4)

        # Detect if popup opened
        pages = context.pages
        if len(pages) > 1:
            auth_page = pages[-1]
        else:
            auth_page = page

        print("Submitting credentials...")

        auth_page.wait_for_selector('input[type="email"]', timeout=30000)

        auth_page.fill('input[type="email"]', EMAIL)
        auth_page.fill('input[type="password"]', PASSWORD)

        auth_page.keyboard.press("Enter")

        print("Waiting for login confirmation...")

        page.wait_for_selector("button:has-text('CART')", timeout=60000)

        context.storage_state(path=SESSION_FILE)

        print("Login successful")

        return True

    except Exception as e:
        print(f"Login failed: {e}")
        return False

    finally:
        context.close()


def claim_rewards(page):
    print("Scanning for free rewards...")

    time.sleep(8)

    claimed = 0

    while claimed < 20:
        buttons = page.locator("button").filter(
            has_text=re.compile("GET FREE", re.I)
        )

        if buttons.count() == 0:
            print("No more rewards found")
            break

        try:
            target = buttons.first

            print(f"Claiming reward #{claimed + 1}")

            target.scroll_into_view_if_needed()
            target.click(force=True)

            time.sleep(5)

            page.keyboard.press("Escape")

            time.sleep(3)

            claimed += 1

        except:
            print("Action blocked, refreshing...")

            page.reload()

            time.sleep(8)

    print(f"Total rewards claimed: {claimed}")


def run():
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        if login_and_save(browser):

            context = browser.new_context(storage_state=SESSION_FILE)

            page = context.new_page()

            try:
                page.goto(
                    "https://store.playcontestofchampions.com/",
                    wait_until="networkidle"
                )

                claim_rewards(page)

            except Exception as e:
                print(f"Claim error: {e}")

            finally:
                context.close()

        else:
            print("Login failed, stopping script")

        browser.close()


if __name__ == "__main__":
    run()
