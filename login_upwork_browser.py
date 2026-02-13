#!/usr/bin/env python3
"""
Launch browser with dedicated Playwright profile to log into Upwork.

Run this ONCE to log into Upwork, then the pipeline can reuse the session.

Usage:
    python login_upwork_browser.py
"""

import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / ".tmp" / "upwork_browser_profile"

async def main():
    print(f"Launching browser with profile: {PROFILE_DIR}")
    print("=" * 60)
    print("1. Log into Upwork in the browser that opens")
    print("2. Make sure you're fully logged in (can see your dashboard)")
    print("3. Close the browser when done")
    print("=" * 60)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Launch browser with persistent context (saves cookies/session)
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,  # Show browser so user can log in
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
            viewport={"width": 1280, "height": 900},
        )

        # Open Upwork login page
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.upwork.com/ab/account-security/login")

        print("\nBrowser opened. Log into Upwork, then close the browser.")
        print("Your session will be saved for future pipeline runs.")

        # Wait for user to close browser
        try:
            await page.wait_for_event("close", timeout=600000)  # 10 min timeout
        except:
            pass

        await context.close()

    print("\nDone! Your Upwork session is saved.")
    print("You can now run the pipeline with URL import.")

if __name__ == "__main__":
    asyncio.run(main())
