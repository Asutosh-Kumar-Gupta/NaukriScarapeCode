from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import BrowserContext, Page
from loguru import logger

from src.scraper.browser import human_delay

_SESSION_FILE = "data/naukri_session.json"


async def login(context: BrowserContext) -> Page:
    """Always do a fresh Google login — no session restore."""
    # Wipe any stale session so browser.py always opens visibly
    _delete_session()

    page = await context.new_page()

    logger.info("Opening Naukri login page...")
    await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=30_000)
    await human_delay(1000, 1500)

    # Click "Continue with Google" if present
    google_btn = page.locator(
        "button:has-text('Google'), a:has-text('Google'), "
        "[class*='google'], button[data-ga-track*='google']"
    )
    if await google_btn.count() > 0:
        logger.info("Clicking 'Continue with Google'...")
        await google_btn.first.click()
        await human_delay(1500, 2500)

    # Wait up to 3 minutes for Google sign-in to complete
    logger.info("Waiting for Google sign-in (up to 3 minutes)...")
    for _ in range(36):
        await page.wait_for_timeout(5_000)
        url = page.url
        if (
            "naukri.com" in url
            and "nlogin" not in url
            and "accounts.google" not in url
        ):
            if await _is_logged_in(page):
                break
        logger.debug(f"Waiting... {url[:70]}")

    if not await _is_logged_in(page):
        raise RuntimeError(
            "Login timed out after 3 minutes. "
            "Complete the Google sign-in in the browser window."
        )

    # Save session for use within this run (API calls, apply steps)
    await _save_session(context)
    logger.success("Logged in. Session saved for this run.")
    return page


async def _is_logged_in(page: Page) -> bool:
    try:
        login_cta = await page.locator(
            "a[href*='nlogin'], button:has-text('Login'), a:has-text('Login')"
        ).count()
        return login_cta == 0
    except Exception:
        return False


async def _save_session(context: BrowserContext) -> None:
    path = Path(_SESSION_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    storage = await context.storage_state()
    with open(path, "w") as f:
        json.dump(storage, f)


def _delete_session() -> None:
    path = Path(_SESSION_FILE)
    if path.exists():
        path.unlink()
        logger.debug("Old session cleared.")
