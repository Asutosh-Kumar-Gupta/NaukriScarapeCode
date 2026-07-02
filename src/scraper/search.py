from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Page, Response
from loguru import logger

from src.core.config import get_settings
from src.scraper.browser import human_delay


@dataclass
class SearchResult:
    job_id: str
    title: str
    company: str
    location: str
    experience: str
    salary: str
    skills: str
    url: str
    posted_date: str
    applicant_count: str
    is_easy_apply: bool = False
    description: str = ""


def _build_search_url(keyword: str, location: str, exp_min: int, exp_max: int) -> str:
    kw_slug = re.sub(r"\s+", "-", keyword.strip().lower())
    loc_slug = re.sub(r"\s+", "-", location.strip().lower())
    return (
        f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}"
        f"?experienceMin={exp_min}&experienceMax={exp_max}&sort=f"
    )


async def search_jobs(page: Page, keyword: str) -> list[SearchResult]:
    settings = get_settings()
    url = _build_search_url(
        keyword,
        settings.search_location,
        settings.search_experience_min,
        settings.search_experience_max,
    )
    logger.info(f"Searching: {keyword} | URL: {url}")

    all_results: list[SearchResult] = []

    for page_num in range(1, settings.search_max_pages + 1):
        page_url = url if page_num == 1 else f"{url}&pageNo={page_num}"
        results, total = await _scrape_page(page, page_url, keyword, page_num)
        if not results:
            break
        all_results.extend(results)
        pages_needed = (total // 20) + 1 if total else settings.search_max_pages
        logger.debug(f"  Page {page_num}/{min(pages_needed, settings.search_max_pages)}: {len(results)} jobs (total available: {total})")
        if total and len(all_results) >= total:
            break
        await human_delay(1500, 2500)

    logger.info(f"Found {len(all_results)} jobs for '{keyword}'")
    return all_results


async def _scrape_page(page: Page, url: str, keyword: str, page_num: int) -> tuple[list[SearchResult], int]:
    captured: list[dict] = []

    async def handle_response(response: Response) -> None:
        if "jobapi" in response.url and response.status == 200:
            try:
                data = await response.json()
                captured.append(data)
            except Exception:
                pass

    page.on("response", handle_response)
    try:
        await page.goto(url, wait_until="networkidle", timeout=40_000)
        await human_delay(2000, 3000)
    finally:
        page.remove_listener("response", handle_response)

    for data in captured:
        # Save raw sample on first page for debugging
        if page_num == 1:
            jobs_sample = data.get("jobDetails", [])
            if jobs_sample:
                Path("logs").mkdir(exist_ok=True)
                Path("logs/api_job_sample.json").write_text(
                    json.dumps(jobs_sample[0], indent=2)
                )
                logger.debug("Raw API sample saved → logs/api_job_sample.json")

        results = _parse_api_response(data)
        if results:
            total = int(
                data.get("noOfJobs")
                or data.get("totalCount")
                or data.get("count")
                or 0
            )
            return results, total

    # Fallback: DOM extraction
    results = await _extract_from_dom(page)
    if results:
        return results, 0

    await _dump_debug_html(page, keyword, page_num)
    return [], 0


def _parse_api_response(data: dict) -> list[SearchResult]:
    job_list = data.get("jobDetails") or []
    if not job_list:
        return []

    results = []
    for job in job_list:
        if not isinstance(job, dict):
            continue
        title = job.get("title", "")
        if not title:
            continue

        jid = str(job.get("jobId", ""))
        url = job.get("jdURL", "") or job.get("url", "")
        if url and not url.startswith("http"):
            url = "https://www.naukri.com" + url
        if not url and jid:
            url = f"https://www.naukri.com/job-listings-{jid}"

        placeholders = job.get("placeholders", [])
        location = _placeholder(placeholders, "location")
        exp      = _placeholder(placeholders, "experience")
        salary   = _placeholder(placeholders, "salary")

        # Skills: Naukri uses "tagsAndSkills" (comma string) in the actual API
        skills_raw = (
            job.get("tagsAndSkills")           # ← real field name from API
            or job.get("tagsAndKeywords")
            or job.get("skillsAndKeywords")
            or []
        )
        skills = skills_raw if isinstance(skills_raw, str) else ", ".join(skills_raw)

        # Job description is included inline in search results
        description = (
            job.get("jobDescription", "")      # ← real field name from API
            or job.get("description", "")
        )

        company    = job.get("companyName", "")
        posted     = job.get("footerPlaceholderLabel", "") or job.get("createdDate", "")
        applicants = str(job.get("applicantCount", "") or "")

        footer = str(posted).lower()
        easy = bool(
            job.get("jobApplyType") == "quickApply"   # ← real field name from API
            or job.get("easyApplyAction")
            or job.get("isEasyApply")
            or job.get("quickApply")
            or job.get("applyType") in ("EASY", "QUICK")
            or "quick" in str(job.get("applyButtonText", "")).lower()
            or "quick apply" in footer
            or "easy apply" in footer
        )

        if not jid:
            m = re.search(r"-(\d{6,})(?:[?#]|$)", url)
            jid = m.group(1) if m else re.sub(r"[^a-zA-Z0-9]", "", url)[-20:]

        results.append(SearchResult(
            job_id=jid,
            title=title,
            company=company,
            location=location,
            experience=exp,
            salary=salary,
            skills=skills,
            description=description,
            url=url,
            posted_date=str(posted),
            applicant_count=applicants,
            is_easy_apply=easy,
        ))
    return results


def _placeholder(placeholders: list, ptype: str) -> str:
    for p in placeholders:
        if isinstance(p, dict) and p.get("type") == ptype:
            return p.get("label", "")
    return ""


async def _extract_from_dom(page: Page) -> list[SearchResult]:
    """DOM fallback using confirmed class patterns from debug HTML."""
    try:
        await page.wait_for_selector("div.flex.cursor-pointer.rounded-3xl", timeout=8_000)
    except Exception:
        return []

    raw = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('div.flex.cursor-pointer.rounded-3xl');
            return Array.from(cards).map(card => {
                const titleEl = card.querySelector('div[class*="text-title18Sb"][class*="text-n100"]');
                const companyEl = card.querySelector('div[class*="text-title16Sb"][class*="text-n200"]');
                const spans = Array.from(
                    card.querySelectorAll('span[class*="text-body14R"][class*="text-n300"]')
                ).map(s => s.innerText.trim()).filter(Boolean);
                const postedEl = card.querySelector('p[class*="text-body12R"]');
                const cardText = card.innerText.toLowerCase();
                return {
                    title:     titleEl   ? titleEl.innerText.trim()  : '',
                    company:   companyEl ? companyEl.innerText.trim() : '',
                    spans:     spans,
                    posted:    postedEl  ? postedEl.innerText.trim()  : '',
                    easyApply: cardText.includes('quick apply') || cardText.includes('easy apply'),
                };
            });
        }
    """)

    results = []
    for item in raw:
        title = item.get("title", "")
        if not title:
            continue
        spans    = item.get("spans", [])
        location = spans[0] if len(spans) > 0 else ""
        salary   = spans[1] if len(spans) > 1 else ""
        skills   = spans[2] if len(spans) > 2 else ""
        exp      = spans[3] if len(spans) > 3 else ""
        job_id   = re.sub(r"[^a-zA-Z0-9]", "", title + item.get("company", ""))[:20]
        results.append(SearchResult(
            job_id=job_id, title=title, company=item.get("company", ""),
            location=location, experience=exp, salary=salary, skills=skills,
            url="", posted_date=item.get("posted", ""), applicant_count="",
            is_easy_apply=item.get("easyApply", False),
        ))
    return results


async def _dump_debug_html(page: Page, keyword: str, page_num: int) -> None:
    try:
        slug = re.sub(r"\s+", "_", keyword.lower())
        path = Path("logs") / f"debug_{slug}_p{page_num}.html"
        path.parent.mkdir(exist_ok=True)
        html = await page.content()
        if len(html) < 1000:
            logger.warning(f"Page returned only {len(html)} bytes — likely blocked by CDN. Try running with HEADLESS=false.")
        path.write_text(html, encoding="utf-8")
        logger.warning(f"0 jobs found — debug HTML saved to {path}")
    except Exception as e:
        logger.debug(f"Could not dump HTML: {e}")


async def fetch_job_description(page: Page, url: str) -> str:
    if not url:
        return ""
    try:
        captured: list[str] = []

        async def handle(response: Response) -> None:
            if "jobapi" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    desc = (
                        data.get("jobDescription", "")
                        or data.get("description", "")
                        or data.get("data", {}).get("jobDescription", "")
                    )
                    if desc:
                        captured.append(desc)
                except Exception:
                    pass

        page.on("response", handle)
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await human_delay(1000, 1500)
        finally:
            page.remove_listener("response", handle)

        if captured:
            return captured[0][:3000]

        for sel in ["[class*='job-desc']", "[class*='jd-desc']", "[class*='job-description']"]:
            el = await page.query_selector(sel)
            if el:
                return (await el.inner_text()).strip()[:3000]
    except Exception as e:
        logger.debug(f"JD fetch failed {url}: {e}")
    return ""
