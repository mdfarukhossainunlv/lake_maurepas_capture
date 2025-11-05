# capture_buoy.py
import os, asyncio, time, traceback
from datetime import datetime
from playwright.async_api import async_playwright
import pytz

# Local timezone (Baton Rouge)
ZONE = pytz.timezone("America/Chicago")

URL = "https://www.southeastern.edu/college-of-science-and-technology/center-for-environmental-research/lakemaurepas/buoydata/"
OUT_DIR = "captures"
os.makedirs(OUT_DIR, exist_ok=True)

SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Safari/605.1.15"
)

MIN_BYTES = 10_000

def exists_ok(path: str, min_bytes: int = MIN_BYTES) -> bool:
    return os.path.exists(path) and os.path.getsize(path) >= min_bytes

# -----------------------
# Robust readiness helpers
# -----------------------

async def wait_dom_complete(page, timeout_ms=60000):
    await page.wait_for_function("document.readyState === 'complete'", timeout=timeout_ms)

async def wait_network_idle(page, timeout_ms=30000):
    # Playwright-level network idle
    await page.wait_for_load_state("networkidle", timeout=timeout_ms)

async def smooth_scroll(page, extra_px=2000, step=400, pause_ms=250):
    # Trigger lazy content
    try:
        total_h = await page.evaluate("document.documentElement.scrollHeight") or 4000
    except Exception:
        total_h = 4000
    y = 0
    while y < total_h + extra_px:
        await page.evaluate(f"window.scrollTo(0, {y});")
        await page.wait_for_timeout(pause_ms)
        y += step
    await page.evaluate("window.scrollTo(0, 0);")
    await page.wait_for_timeout(800)

async def wait_no_spinners(page, timeout_ms=45000):
    # No spinner classes & no visible "loading" text
    sel_js = """
        () => {
          const visible = el => !!el && el.offsetParent !== null;
          const spinSel = '.loading, .spinner, .lds-ring, .lds-spinner, [aria-busy="true"]';
          const spinners = Array.from(document.querySelectorAll(spinSel)).filter(visible);
          const hasLoadingText = Array.from(document.querySelectorAll('body *'))
            .some(n => /loading/i.test(n.textContent || ''));
          return spinners.length === 0 && !hasLoadingText;
        }
    """
    await page.wait_for_function(sel_js, timeout=timeout_ms)

async def wait_iframes_ready(page, timeout_ms=45000):
    # Ensure each iframe's body exists and has no obvious spinners/loading text
    frames = await page.query_selector_all("iframe")
    for i, el in enumerate(frames):
        try:
            frame = await el.content_frame()
            if not frame:
                continue
            await frame.wait_for_selector("body", timeout=timeout_ms)
            await frame.wait_for_function(
                """() => {
                    const visible = el => !!el && el.offsetParent !== null;
                    const spinSel = '.loading, .spinner, .lds-ring, .lds-spinner, [aria-busy="true"]';
                    const spinners = Array.from(document.querySelectorAll(spinSel)).filter(visible);
                    const hasLoadingText = Array.from(document.querySelectorAll('body *'))
                        .some(n => /loading/i.test(n.textContent || ''));
                    return spinners.length === 0 && !hasLoadingText;
                }""",
                timeout=timeout_ms
            )
        except Exception:
            print(f"[WARN] iframe #{i} did not fully settle before timeout.")

async def count_graph_nodes(page):
    return await page.evaluate("document.querySelectorAll('svg, canvas').length")

async def wait_stable_graph_count(page, stable_ms=2000, poll_ms=200, min_nodes=4, timeout_ms=45000):
    """
    Wait until svg/canvas count >= min_nodes and remains unchanged for stable_ms.
    """
    start = time.time()
    last_count = -1
    stable_start = None
    while (time.time() - start) * 1000 < timeout_ms:
        curr = await count_graph_nodes(page)
        if curr >= min_nodes:
            if curr == last_count:
                if stable_start is None:
                    stable_start = time.time()
                elapsed = (time.time() - stable_start) * 1000
                if elapsed >= stable_ms:
                    return
            else:
                stable_start = None
        last_count = curr
        await page.wait_for_timeout(poll_ms)
    raise TimeoutError(f"svg/canvas count not stable (>= {min_nodes}) within {timeout_ms} ms")

async def wait_all_images_decoded(page, timeout_ms=45000):
    # Wait until all images in the main document are fully decoded
    await page.wait_for_function(
        """async () => {
            const imgs = Array.from(document.images || []);
            await Promise.all(imgs.map(img => (img.decode ? img.decode().catch(()=>{}) : Promise.resolve())));
            return true;
        }""",
        timeout=timeout_ms
    )
    # Do the same for iframes (best-effort)
    frames = await page.query_selector_all("iframe")
    for i, el in enumerate(frames):
        try:
            frame = await el.content_frame()
            if not frame:
                continue
            await frame.wait_for_function(
                """async () => {
                    const imgs = Array.from(document.images || []);
                    await Promise.all(imgs.map(img => (img.decode ? img.decode().catch(()=>{}) : Promise.resolve())));
                    return true;
                }""",
                timeout=timeout_ms
            )
        except Exception:
            print(f"[WARN] iframe images not fully decoded before timeout for iframe #{i}")

# -----------------------
# Main capture
# -----------------------

async def take_capture():
    now_local = datetime.now(ZONE)
    ts_local = now_local.strftime("%Y%m%d_%H%M%S")
    base = os.path.join(OUT_DIR, f"buoy_{ts_local}_BatonRouge")
    png_path = f"{base}.png"
    pdf_path = f"{base}.pdf"

    print("========================================")
    print(f"[INFO] Baton Rouge local time: {now_local.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    print(f"[INFO] Output:\n  PNG: {png_path}\n  PDF: {pdf_path}")
    print("========================================")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 2400, "height": 1400},  # wide so 4 columns fit
            user_agent=SAFARI_UA,
            ignore_https_errors=True,
            locale="en-US",
            accept_downloads=True,
        )
        page = await context.new_page()

        print("[STEP] goto …")
        await page.goto(URL, wait_until="domcontentloaded", timeout=180000)

        print("[STEP] wait DOM complete …")
        await wait_dom_complete(page)

        print("[STEP] network idle …")
        await wait_network_idle(page)

        print("[STEP] initial settle 2s …")
        await page.wait_for_timeout(2000)

        print("[STEP] scroll to trigger lazy content …")
        await smooth_scroll(page, extra_px=2500, step=450, pause_ms=250)

        print("[STEP] ensure iframes are ready …")
        await wait_iframes_ready(page)

        print("[STEP] ensure no spinners/loading …")
        await wait_no_spinners(page)

        print("[STEP] wait stable svg/canvas count …")
        await wait_stable_graph_count(page, stable_ms=2000, poll_ms=200, min_nodes=4, timeout_ms=45000)

        print("[STEP] wait all images decoded …")
        await wait_all_images_decoded(page)

        # One last tiny settle
        await page.wait_for_timeout(500)

        # ---- Full-page PNG (complete height) ----
        print("[STEP] save full-page PNG …")
        await page.screenshot(path=png_path, full_page=True)
        if not exists_ok(png_path):
            raise RuntimeError("PNG capture failed or too small.")

        # ---- Width-fit PDF (A2 landscape, automatic vertical pagination) ----
        print("[STEP] save PDF (A2 landscape, fit width) …")
        try:
            content_width_px = await page.evaluate("document.documentElement.scrollWidth") or 2400
        except Exception:
            content_width_px = 2400
        target_width_px = 2400
        scale = min(1.0, target_width_px / max(content_width_px, 1))
        await page.pdf(
            path=pdf_path,
            format="A2",
            landscape=True,
            print_background=True,
            margin={"top": "0.3in", "right": "0.3in", "bottom": "0.3in", "left": "0.3in"},
            prefer_css_page_size=False,
            scale=scale,
        )
        if not exists_ok(pdf_path):
            print("[WARN] PDF tiny/missing; PNG is still available.")

        await browser.close()

    print(f"[OK] PNG saved → {png_path} ({os.path.getsize(png_path)/1024:.1f} KB)")
    if exists_ok(pdf_path):
        print(f"[OK] PDF saved  → {pdf_path} ({os.path.getsize(pdf_path)/1024:.1f} KB)")
    print("[DONE] Capture complete.")
    return png_path, pdf_path

async def main():
    await take_capture()

if __name__ == "__main__":
    asyncio.run(main())
