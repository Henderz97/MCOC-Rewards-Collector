def claim_rewards(page):
    print("Scanning for rewards...")
    # Wait for the main store grid to actually exist
    try:
        page.wait_for_selector("[class*='store-grid'], [class*='item-card']", timeout=20000)
    except:
        print("Warning: Store grid not found, trying to scan anyway...")

    # Accept cookies if the popup appears
    try:
        cookie_btn = page.get_by_role("button", name="ACCEPT ALL").first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(2000)
    except: pass

    # Slow scroll to trigger lazy loading
    for i in range(5):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(1)

    claimed = 0
    max_attempts = 10
    
    while claimed < max_attempts:
        # NEW SELECTOR: Look for buttons that contain these words anywhere in their text
        # Also specifically targeting the 'unit-price' area where 'FREE' usually hides
        selector = "button:has-text('FREE'), button:has-text('GET'), button:has-text('CLAIM'), [role='button']:has-text('FREE')"
        buttons = page.locator(selector)
        count = buttons.count()
        
        print(f"Found {count} potential buttons on screen...")
        
        target_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible() or not btn.is_enabled():
                    continue

                txt = btn.inner_text().upper()
                parent_text = btn.locator("xpath=..").inner_text().upper()

                # LOGGING: Let's see what we are skipping
                # print(f"Checking button {i}: '{txt}'")

                # Filter out currency/subscriptions
                if "$" in txt or "MONTH" in txt or "UNIT" in txt:
                    continue
                
                # Filter out locked milestones
                if "MORE MARKET POINTS" in parent_text:
                    continue

                # If we made it here, it's a valid FREE item
                target_btn = btn
                break
            except: continue
        
        if not target_btn:
            print("No more valid items found in this pass.")
            break

        try:
            print(f"Attempting to click item #{claimed + 1}...")
            target_btn.scroll_into_view_if_needed()
            # Try a standard click first, then force if needed
            target_btn.click(timeout=5000)
            page.wait_for_timeout(5000)
            
            # Close the 'Success' or 'Claimed' popup
            # Usually there is an 'X' or we can just press Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(2000)
            
            claimed += 1
            save_debug_info(page, f"after_claim_{claimed}")
        except Exception as e:
            print(f"Click failed: {e}")
            # Try a forced click as fallback
            try:
                target_btn.click(force=True)
                claimed += 1
            except:
                break

    if claimed > 0:
        send_telegram_msg(f"✅ Successfully claimed {claimed} rewards!")
    else:
        # This is where we save a 'not_found' image to see what the script saw
        save_debug_info(page, "nothing_found_debug")
        send_telegram_msg("👀 No rewards found today. Check debug pack.")
    return "SUCCESS"
