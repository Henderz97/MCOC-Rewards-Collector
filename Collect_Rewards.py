def run():
    if not EMAIL or not PASSWORD:
        print("CRITICAL: KABAM_EMAIL or KABAM_PASSWORD secrets are missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # לוגין רק אם אין סשן
        if not os.path.exists(SESSION_FILE):
            print("No session file found. Initiating login...")
            login_and_save(browser)
        else:
            print("Session file found. Skipping login.")

        # יצירת קונטקסט עם הסשן הקיים
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()
        
        try:
            print(f"Opening store: {STORE_URL}")
            page.goto(STORE_URL, wait_until="networkidle")
            
            # צילום מסך מיידי לדיבאג - שנדע מה הבוט רואה בשניה הראשונה
            save_debug_info(page, "0_store_landing_page")
            
            # בדיקה אם אנחנו עדיין מחוברים
            if page.locator("text=CART").count() == 0:
                print("Session expired or invalid. Re-logging...")
                context.close()
                login_and_save(browser)
                context = browser.new_context(storage_state=SESSION_FILE)
                page = context.new_page()
                page.goto(STORE_URL, wait_until="networkidle")
                save_debug_info(page, "0_store_after_relog")

            claim_rewards(page)
            
        except Exception as e:
            print(f"CRITICAL RUNTIME ERROR: {e}")
            save_debug_info(page, "runtime_fatal_error")
        finally:
            browser.close()
            print("Process finished.")
