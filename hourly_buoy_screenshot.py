import os, asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import pytz

URL = "https://www.southeastern.edu/college-of-science-and-technology/center-for-environmental-research/lakemaurepas/buoydata/"
OUT_DIR = "captures"
os.makedirs(OUT_DIR, exist_ok=True)

SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Safari/605.1.15"
)

async def take_pdf_snapshot():
    # timestamp in America/Chicago
    central = pytz.timezone("America/Chicago")
    now = datetime.now(central)
    ts = now.strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUT_DIR, f"buoy_{ts}.pdf")

    print(f"[INFO] Capturing page at {now}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            viewport={"width":1920,"height":1080},
            user_agent=SAFARI_UA,
            ignore_https_errors=True,
            locale="en-US",
            accept_downloads=True,
        )

        page = await context.new_page()

        # Load page with a softer wait
        print("[STEP] Loading page (domcontentloaded)...")
        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=180000  # 180 seconds
        )

        # Give charts/iframes a chance to render
        print("[STEP] Waiting for render...")
        await page.wait_for_timeout(8000)

        # Try to scroll to trigger lazy loading
        print("[STEP] Scrolling page...")
        try:
            scroll_height = await page.evaluate("document.body.scrollHeight")
        except Exception:
            scroll_height = 2000
        current_y = 0
        step = 300
        while current_y < scroll_height:
            await page.evaluate(f"window.scrollTo(0, {current_y});")
            await page.wait_for_timeout(1000)
            current_y += step

        # back to top
        await page.evaluate("window.scrollTo(0,0);")
        await page.wait_for_timeout(2000)

        # Compute full page size
        scroll_width = await page.evaluate("document.documentElement.scrollWidth")
        scroll_height = await page.evaluate("document.documentElement.scrollHeight")

        # Save PDF (no cropping)
        print("[STEP] Generating PDF...")
        await page.pdf(
            path=out_file,
            width=f"{scroll_width}px",
            height=f"{scroll_height}px",
            print_background=True,
            margin={
                "top": "0",
                "right": "0",
                "bottom": "0",
                "left": "0"
            },
            prefer_css_page_size=True
        )

        await browser.close()

    print(f"[OK] Saved {out_file}")
    # Return the file path so the workflow can use it
    return out_file

async def main():
    await take_pdf_snapshot()

if __name__ == "__main__":
    asyncio.run(main())
