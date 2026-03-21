from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # Capture console API calls
        page.on("console", lambda msg: print(f"Console {msg.type}: {msg.text}"))
        
        # Capture uncaught page errors
        page.on("pageerror", lambda err: print(f"Page Error: {err}"))
        
        print("Navigating to localhost:5174...")
        page.goto("http://localhost:5174/", wait_until="networkidle")
        print("Done.")
        browser.close()

if __name__ == "__main__":
    run()
