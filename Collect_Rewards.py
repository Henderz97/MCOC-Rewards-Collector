import os
import time
from playwright.sync_api import sync_playwright, TimeoutError

EMAIL = os.getenv("KABAM_EMAIL")
PASSWORD = os.getenv("KABAM_PASSWORD")
SESSION_FILE = "kabam_session.json"

def login_and_save(browser):

    context = browser.new_context()
    page = context.new_page()

    print("Starting login process...")

    # IMPORTANT: do NOT use networkidle
    page.goto(
        "https://store.playcontestofchampions.com/",
        wait_until="domcontentloaded",
        timeout=60000
    )

    time.sleep(3)

    # Click the top login button
    page.locator("text=Log in").first.click()

    popup = None

    try:
        popup = page.wait_for_event("popup", timeout=8000)
        login_page = popup
        print("Popup login detected.")
    except TimeoutError:
        login_page = page
        print("No popup. Using same page login.")

    try:
        login_page.wait_for_selector('input[type="email"]', timeout=30000)

        login_page.fill('input[type="email"]', EMAIL)
        login_page.fill('input[type="password"]', PASSWORD)

        login_page.locator("button:has-text('Log In')").click()

        time.sleep(5)

        context.storage_state(path=SESSION_FILE)

        print("Login successful. Session saved.")

    except TimeoutError:
        print("Login fields never appeared.")
        login_page.screenshot(path="login_error.png")
        raise

    if popup:
        popup.close()

    context.close()


def run():

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        if not os.path.exists(SESSION_FILE):
            login_and_save(browser)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        print("Opening store page...")

        page.goto(
            "https://store.playcontestofchampions.com/",
            wait_until="domcontentloaded",
            timeout=60000
        )

        time.sleep(5)

        print("Scanning for rewards...")

        buttons = page.locator("button:has-text('Get')")

        count = buttons.count()

        for i in range(count):
            try:
                buttons.nth(i).click()
                time.sleep(2)
            except:
                pass

        print("Finished collecting rewards.")

        browser.close()


if name == "main":
    run()
