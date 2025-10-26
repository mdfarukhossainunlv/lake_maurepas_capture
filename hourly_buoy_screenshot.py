import os, math, asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import pytz
import subprocess

URL = "https://www.southeastern.edu/college-of-science-and-technology/center-for-environmental-research/lakemaurepas/buoydata/"
OUT_DIR = "captures"
os.makedirs(OUT_DIR, exist_ok=True)

SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Safari/605.1.15"
)

async def take_pdf_snapshot():
    central = pytz.timezone("America/Chicago")
    now = datetime.now(central)
    ts = now.strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(OUT_DIR, f"buoy_{ts}.pdf")

    print(f"[INFO] Capturing page at {now}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context(
            viewport={"width":1920,"height":1080},
            user_agent=SAFARI_UA,
            ignore_https_errors=True)).new_page()
        await page.goto(URL, wait_until="networkidle", timeout=120000)
        await page.wait_for_timeout(5000)
        await page.pdf(path=out_file, format="A4", print_background=True)
        await browser.close()

    subprocess.run(["git","config","user.email","github-bot@example.com"],check=True)
    subprocess.run(["git","config","user.name","buoy-bot"],check=True)
    subprocess.run(["git","add",out_file],check=True)
    subprocess.run(["git","commit","-m",f"Add buoy snapshot {os.path.basename(out_file)}"],check=True)

asyncio.run(take_pdf_snapshot())
