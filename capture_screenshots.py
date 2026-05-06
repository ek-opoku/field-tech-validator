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
        
        # 1. Dashboard
        print("Navigating to Dashboard...")
        page.goto(BASE_URL, timeout=60000)
        time.sleep(10)
        page.screenshot(path="assets/tutorial_dashboard.png")
        
        # 2. Field Data Collection (Prep Route)
        print("Navigating to Field Data Collection...")
        page.goto(f"{BASE_URL}/Field_Data_Collection", timeout=60000)
        time.sleep(8)
        try:
            page.click('text="➕ Add New Site Manually"', timeout=3000)
            time.sleep(2)
        except Exception as e: print(e)
        page.screenshot(path="assets/tutorial_prep_route.png")
        
        # 3. Field Data Collection (Params)
        print("Switching to Params tab...")
        try:
            page.click('button[data-baseweb="tab"]:has-text("⚙️ Parameters & Settings")', timeout=3000)
            time.sleep(2)
            page.click('text="Advanced Configuration"', timeout=3000)
            time.sleep(2)
        except Exception as e: print(e)
        page.screenshot(path="assets/tutorial_prep_params.png")
        
        # 4. Field Data Collection (SOP)
        print("Switching to SOP tab...")
        try:
            page.click('button[data-baseweb="tab"]:has-text("📝 Instructions")', timeout=3000)
            time.sleep(2)
        except Exception as e: print(e)
        page.screenshot(path="assets/tutorial_prep_sop.png")
        
        # Switch back to route to begin trip
        try:
            page.click('button[data-baseweb="tab"]:has-text("📍 Route & Sites")', timeout=3000)
            time.sleep(2)
        except: pass

        # 5. Field Data Collection (Active Sampling QAQC)
        print("Starting a trip...")
        try:
            page.click('button:has-text("Begin Trip")', timeout=3000)
            time.sleep(8)
            
            # Type 14 into pH
            # Streamlit inputs are tricky. Let's just type into the first number input.
            inputs = page.query_selector_all('input[type="number"]')
            if inputs:
                inputs[0].fill("14")
                page.keyboard.press("Enter")
                time.sleep(3)
            page.screenshot(path="assets/tutorial_sampling_qaqc.png")
            
            # 6. Field Data Collection (SOP Assistant)
            page.click('text="📖 SOP Quick Reference"', timeout=3000)
            time.sleep(2)
            page.screenshot(path="assets/tutorial_sampling_assistant.png")
        except Exception as e:
            print(f"Failed during sampling phase: {e}")

        # 7. Gateway Sync
        print("Navigating to Gateway Sync...")
        page.goto(f"{BASE_URL}/Gateway_Sync", timeout=60000)
        time.sleep(8)
        page.screenshot(path="assets/tutorial_sync.png")
        
        # 8. Chain of Custody
        print("Navigating to Chain of Custody...")
        page.goto(f"{BASE_URL}/Chain_of_Custody", timeout=60000)
        time.sleep(8)
        page.screenshot(path="assets/tutorial_coc.png")
        
        browser.close()

if __name__ == "__main__":
    take_screenshots()
