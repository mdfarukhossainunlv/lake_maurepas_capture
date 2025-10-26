import os, asyncio, subprocess
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
        # launch browser headless
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

        # softer wait: domcontentloaded, longer timeout
        print("[STEP] Loading page (domcontentloaded)...")
        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=180000  # 180 sec
        )

        # give the page time to render charts / iframes
        print("[STEP] Waiting for render...")
        await page.wait_for_timeout(8000)

        # scroll slowly to trigger lazy content
        print("[STEP] Scrolling page to load dynamic sections...")
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

        # make PDF
        print("[STEP] Generating PDF...")
        await page.pdf(
            path=out_file,
            format="A4",
            print_background=True,
            margin={
                "top": "0.5in",
                "right": "0.5in",
                "bottom": "0.5in",
                "left": "0.5in"
            },
        )

        await browser.close()

    print(f"[OK] Saved {out_file}")

    # stage + commit this new PDF in git (push happens in workflow, not here)
    print("[STEP] Commit PDF to repo history...")
    subprocess.run(["git","config","user.email","github-bot@example.com"],check=True)
    subprocess.run(["git","config","user.name","buoy-bot"],check=True)
    subprocess.run(["git","add",out_file],check=True)
    subprocess.run(
        ["git","commit","-m",f"Add buoy snapshot {os.path.basename(out_file)}"],
        check=True
    )
    print("[OK] Commit created")

async def main():
    await take_pdf_snapshot()

if __name__ == "__main__":
    asyncio.run(main())
