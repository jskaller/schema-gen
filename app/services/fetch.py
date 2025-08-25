from typing import Optional
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext
import asyncio

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 15_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

@asynccontextmanager
async def _context(headless: bool = True) -> BrowserContext:
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(user_agent=DEFAULT_UA)
        try:
            yield ctx
        finally:
            await ctx.close()
            await browser.close()

async def fetch_url(url: str, timeout_ms: int = 30000, wait_until: str = "load") -> str:
    """
    Fetch a URL with Chromium and return the rendered HTML.
    """
    async with _context(headless=True) as ctx:
        page = await ctx.new_page()
        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        # Let lazy content settle a bit without blocking forever
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        html = await page.content()
        return html

def fetch_url_sync(url: str, timeout_ms: int = 30000, wait_until: str = "load") -> str:
    return asyncio.run(fetch_url(url, timeout_ms=timeout_ms, wait_until=wait_until))
