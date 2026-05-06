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
        
        # 2. Field Data Collection (Prep Phase)
        print("Navigating to Field Data Collection...")
        page.goto(f"{BASE_URL}/Field_Data_Collection", timeout=60000)
        time.sleep(10)
        page.screenshot(path="assets/tutorial_prep.png")
        
        # 3. Field Data Collection (Active Sampling)
        print("Starting a trip...")
        try:
            page.click('button:has-text("Begin Trip")', timeout=3000)
            time.sleep(5)
            page.screenshot(path="assets/tutorial_sampling.png")
        except Exception as e:
            print(f"Failed to start trip: {e}")
            page.screenshot(path="assets/tutorial_sampling.png")

        # 4. Gateway Sync
        print("Navigating to Gateway Sync...")
        page.goto(f"{BASE_URL}/Gateway_Sync", timeout=60000)
        time.sleep(10)
        page.screenshot(path="assets/tutorial_sync.png")
        
        # 5. Chain of Custody
        print("Navigating to Chain of Custody...")
        page.goto(f"{BASE_URL}/Chain_of_Custody", timeout=60000)
        time.sleep(10)
        page.screenshot(path="assets/tutorial_coc.png")
        
        browser.close()

if __name__ == "__main__":
    take_screenshots()
