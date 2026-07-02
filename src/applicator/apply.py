from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from loguru import logger

from src.core.config import get_settings
from src.core.database import mark_applied, mark_skipped
from src.core.models import Job
from src.core.profile import get_profile
from src.scraper.browser import human_delay

# All known selectors for the Apply / Quick Apply button across Naukri layouts
_APPLY_BTN_SELECTORS = [
    # New Naukri (2024–2025) — text-based
    "button:has-text('Quick Apply')",
    "button:has-text('Apply Now')",
    "button:has-text('Easy Apply')",
    "button:has-text('Apply')",
    # Class-based fallbacks
    "[class*='apply-btn']",
    "[class*='applyBtn']",
    "[id*='apply-button']",
    "[data-ga-track*='Apply']",
]

_SUCCESS_TEXTS = [
    "successfully applied",
    "application submitted",
    "applied successfully",
    "thank you for applying",
    "you have applied",
    "application received",
]


class ApplyResult:
    def __init__(self, success: bool, reason: str, screenshot: str = ""):
        self.success = success
        self.reason = reason
        self.screenshot = screenshot


async def apply_to_job(page: Page, job: Job) -> ApplyResult:
    settings = get_settings()
    profile = get_profile()

    if job.company.lower() in settings.skip_companies_set:
        mark_skipped(job.job_id, f"Company in skip list: {job.company}")
        return ApplyResult(False, f"Company '{job.company}' in skip list")

    logger.info(f"Applying: [{job.match_score:.0f}%] {job.title} @ {job.company}")

    try:
        await page.goto(job.url, wait_until="networkidle", timeout=30_000)
        await human_delay(2000, 3000)

        # Check already applied
        page_text = (await page.inner_text("body")).lower()
        if "already applied" in page_text or "you have applied" in page_text:
            mark_skipped(job.job_id, "Already applied")
            return ApplyResult(False, "Already applied")

        # Find apply button
        apply_btn = await _find_apply_button(page)
        if not apply_btn:
            ss = await _screenshot(page, job.job_id, "no_btn")
            mark_skipped(job.job_id, "Apply button not found")
            logger.warning(f"  No apply button found on {job.url}")
            return ApplyResult(False, "Apply button not found", ss)

        btn_text = (await apply_btn.inner_text()).strip()
        logger.info(f"  Found button: '{btn_text}'")
        await apply_btn.click()
        await human_delay(2000, 3000)

        # Handle the apply flow (modal or redirect)
        result = await _handle_apply_flow(page, profile)

        if result.success:
            ss = await _screenshot(page, job.job_id, "applied")
            mark_applied(job.job_id, ss)
            logger.success(f"  Applied → {job.title} @ {job.company}")
            return ApplyResult(True, "Applied successfully", ss)
        else:
            mark_skipped(job.job_id, result.reason)
            return result

    except PlaywrightTimeout as e:
        reason = f"Timeout: {e}"
        mark_skipped(job.job_id, reason)
        return ApplyResult(False, reason)
    except Exception as e:
        reason = f"Error: {e}"
        logger.warning(f"  Apply failed: {reason}")
        mark_skipped(job.job_id, reason)
        return ApplyResult(False, reason)


async def _find_apply_button(page: Page):
    """Try each known selector; return the first visible, enabled button."""
    for sel in _APPLY_BTN_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                return btn
        except Exception:
            continue
    # Last resort: any button whose text contains 'apply' (case-insensitive)
    try:
        all_buttons = await page.query_selector_all("button")
        for btn in all_buttons:
            txt = (await btn.inner_text()).strip().lower()
            if "apply" in txt and await btn.is_visible():
                return btn
    except Exception:
        pass
    return None


async def _handle_apply_flow(page: Page, profile) -> ApplyResult:
    """Navigate multi-step Naukri apply modal."""
    for step in range(6):
        await human_delay(1500, 2500)
        page_text = (await page.inner_text("body")).lower()

        # Success check
        if any(s in page_text for s in _SUCCESS_TEXTS):
            return ApplyResult(True, "Submitted")

        if "already applied" in page_text:
            return ApplyResult(False, "Already applied")

        # Autofill visible fields
        await _autofill(page, profile)

        # Find Next / Submit button
        next_btn = await _find_next_button(page)
        if not next_btn:
            # No more steps — check if we're done
            if any(s in page_text for s in _SUCCESS_TEXTS):
                return ApplyResult(True, "Submitted")
            # Detect screening questions we can't auto-answer
            textarea_count = len(await page.query_selector_all("textarea"))
            if textarea_count > 1:
                return ApplyResult(False, "Screening questions — manual review needed")
            return ApplyResult(False, f"No Next/Submit button found at step {step + 1}")

        btn_text = (await next_btn.inner_text()).strip()
        logger.debug(f"  Step {step + 1}: clicking '{btn_text}'")
        await next_btn.click()

    return ApplyResult(False, "Exceeded max steps in apply flow")


async def _find_next_button(page: Page):
    candidates = [
        "button:has-text('Submit')",
        "button:has-text('Apply')",
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "button[type='submit']",
        "[class*='submit-btn']",
    ]
    for sel in candidates:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible() and await btn.is_enabled():
                return btn
        except Exception:
            continue
    return None


async def _autofill(page: Page, profile) -> None:
    try:
        for sel, value in [
            ("input[placeholder*='notice' i], input[name*='notice' i]", str(profile.notice_period_days)),
            ("input[placeholder*='expected' i][placeholder*='salary' i]", str(profile.expected_salary_lpa)),
            ("input[placeholder*='current' i][placeholder*='salary' i]", str(profile.expected_salary_lpa - 5)),
        ]:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                current = await el.input_value()
                if not current:
                    await el.fill(value)
                    await human_delay(200, 400)

        # Cover letter / message box
        msg = page.locator("textarea[placeholder*='message' i], textarea[placeholder*='cover' i]").first
        if await msg.count() > 0 and await msg.is_visible():
            if not await msg.input_value():
                snippet = (
                    f"Hi, I am {profile.name}, a {profile.current_role} with "
                    f"{profile.total_experience_years}+ years of experience in Python, FastAPI, "
                    f"LangChain, AWS and Kubernetes. I am excited about this opportunity."
                )
                await msg.fill(snippet)
    except Exception as e:
        logger.debug(f"Autofill partial error: {e}")


async def _screenshot(page: Page, job_id: str, label: str) -> str:
    settings = get_settings()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = Path(settings.screenshots_path) / f"{job_id}_{label}_{ts}.png"
    try:
        await page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ""
