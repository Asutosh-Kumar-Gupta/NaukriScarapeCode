from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import Browser, BrowserContext, async_playwright
from loguru import logger

from src.core.config import get_settings


@asynccontextmanager
async def get_browser_context(force_visible: bool = False) -> AsyncGenerator[BrowserContext, None]:
    settings = get_settings()
    # Always open visible — required for Google OAuth and to bypass CDN bot detection
    headless = settings.headless and not force_visible

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def human_delay(min_ms: int = 500, max_ms: int = 1500) -> None:
    import random
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)
