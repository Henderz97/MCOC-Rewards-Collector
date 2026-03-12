import os
import re
import time
import json
from playwright.sync_api import sync_playwright

SESSION_FILE = "kabam_session.json"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # INJECT THE SESSION FROM GITHUB SECRETS
        session_data = os.getenv("KABAM_SESSION_JSON")
        if session_data:
            with open(SESSION_FILE, "w") as f:
                f.write(session_data)
        
        # Open browser with your "Logged In" state
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print("Accessing store with existing session...")
            page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
            
            # Check if still logged in
            if "log in" in page.content().lower():
                print("Error: Session expired or invalid.")
                return

            claim_rewards(page)
            
        finally:
            browser.close()

def claim_rewards(page):
    print("Scanning for rewards...")
    time.sleep(10)
    claimed = 0
    while claimed < 20:
        buttons = page.get_by_role("button", name=re.compile("get free", re.I))
        if buttons.count() == 0:
            break
        try:
            buttons.first.click(force=True)
            time.sleep(5)
            page.keyboard.press("Escape")
            time.sleep(2)
            claimed += 1
            print(f"Claimed #{claimed}")
        except:
            page.reload()
            time.sleep(5)
    print(f"Total claimed: {claimed}")

if __name__ == "__main__":
    run()
