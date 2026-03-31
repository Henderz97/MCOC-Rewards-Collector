def login_and_save(browser):
    print("Starting fresh login...")
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    try:
        page.goto(XSOLLA_AUTH_URL, wait_until="networkidle", timeout=60000)
        save_debug_info(page, "login_01_loaded")
        save_html(page, "login_01_loaded")

        page.wait_for_selector('input[type="email"]', timeout=30000)
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        save_debug_info(page, "login_02_filled")

        # Click the Login button explicitly instead of pressing Enter
        login_btn = page.get_by_role("button", name="Login")
        login_btn.click()
        print("Login button clicked.")

        # Wait for redirect back to store
        page.wait_for_url(re.compile(r"store\.playcontestofchampions"), timeout=60000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(7000)
        save_debug_info(page, "login_03_redirected")
        save_html(page, "login_03_redirected")

        # Accept cookies if present before saving session
        try:
            cookie_btn = page.get_by_role("button", name="ACCEPT").first
            if cookie_btn.is_visible():
                cookie_btn.click()
                page.wait_for_timeout(2000)
                print("Cookie banner dismissed during login.")
        except:
            pass

        # Verify we're actually logged in before saving
        page.wait_for_timeout(3000)
        save_debug_info(page, "login_04_final_state")
        save_html(page, "login_04_final_state")

        # Check for any login-related elements still visible
        login_still_visible = False
        try:
            login_still_visible = page.get_by_text("LOG IN").first.is_visible()
        except:
            pass

        if login_still_visible:
            raise Exception("Login appeared to succeed but store still shows logged-out state.")

        context.storage_state(path=SESSION_FILE)
        print("Login success and session saved.")

    except Exception as e:
        save_debug_info(page, "login_fail")
        save_html(page, "login_fail")
        raise e
    finally:
        context.close()
