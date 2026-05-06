from playwright.sync_api import sync_playwright
import time
import os

BASE_URL = "http://localhost:8501"

def take_screenshots():
    os.makedirs("assets", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1'
        )
        page = context.new_page()
        
        print("Navigating to Field Data Collection...")
        page.goto(f"{BASE_URL}/Field_Data_Collection", timeout=60000)
        time.sleep(8)
        
        # We must select a site to optimize. "Choose sites for today:"
        # Let's just click "Optimize Route" since it might have default selections?
        # Actually, `selected_site_ids` defaults to []. We must select one.
        # But wait, there are default preloaded sites. We can click on the multiselect and pick one, or just add a custom site and pick it.
        # Let's add a custom site and optimize route.
        try:
            page.click('text="➕ Add New Site Manually"', timeout=3000)
            time.sleep(1)
            page.fill('input[placeholder="e.g. WELL-999"]', "WELL-1")
            page.click('button:has-text("Add Custom Site")')
            time.sleep(2)
            # Now we must select it in the multiselect
            page.click('div[data-baseweb="select"]')
            time.sleep(1)
            page.click('li[role="option"]')
            time.sleep(1)
            page.click('button:has-text("Optimize Route")')
            time.sleep(3)
        except Exception as e: print(f"Prep error: {e}")

        # Start trip
        try:
            page.click('button:has-text("Begin Trip")', timeout=3000)
            time.sleep(5)
            
            # Type 14 into pH
            page.fill('input[aria-label="pH (standard units)"]', "14")
            page.keyboard.press("Enter")
            time.sleep(3)
            page.screenshot(path="assets/tutorial_sampling_qaqc.png")
            
            # SOP Assistant
            page.click('text="📖 SOP Quick Reference"', timeout=3000)
            time.sleep(2)
            page.screenshot(path="assets/tutorial_sampling_assistant.png")
        except Exception as e:
            print(f"Failed during sampling phase: {e}")
        
        browser.close()

if __name__ == "__main__":
    take_screenshots()
