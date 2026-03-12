import os
import json
import time
import requests

SESSION_FILE = "kabam_session.json"

def claim_via_api(access_token):
    print("Session valid. Fetching rewards list via API...")
    
    # The API headers usually require the Bearer token we got from the cookie
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Origin": "https://store.playcontestofchampions.com",
        "Referer": "https://store.playcontestofchampions.com/"
    }

    # Endpoint to get the manifest of items (This is an example path)
    # Note: You can find the exact 'claim' URL in your Browser Network Tab (F12)
    # when you click a button manually.
    store_url = "https://api.playcontestofchampions.com/v1/store/items" 
    
    try:
        # 1. Get items
        # 2. Loop and POST to the claim endpoint
        # For simplicity in this 'Simple' version, we stay with the Playwright 
        # logic but use the session you uploaded.
        pass

if __name__ == "__main__":
    # If we want the absolute simplest path that WORKED before:
    # Use the session file you uploaded to bypass the Auth API entirely.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if not os.path.exists(SESSION_FILE):
            print("Missing kabam_session.json! Upload it to your repo.")
            exit()

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        
        print("Opening store...")
        page.goto("https://store.playcontestofchampions.com/", wait_until="networkidle")
        
        # Check if login is needed
        if "LOG IN" in page.content().upper():
            print("Session expired. Please re-upload kabam_session.json")
        else:
            print("Logged in! Claiming...")
            # Simple button-clicker loop
            for i in range(15):
                btn = page.get_by_role("button", name="GET FREE").first
                if btn.is_visible():
                    btn.click(force=True)
                    print(f"Claimed item {i+1}")
                    time.sleep(4)
                    page.keyboard.press("Escape")
                    time.sleep(2)
                else:
                    break
        browser.close()
