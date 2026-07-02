from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime

from loguru import logger

from src.core.config import get_settings
from src.core.database import (
    already_applied,
    create_run_log,
    get_pending_jobs,
    init_db,
    job_exists,
    update_run_log,
    upsert_job,
)
from src.core.models import ApplicationStatus, Job
from src.matcher.scorer import MatchResult, score_job, should_apply
from src.scraper.browser import get_browser_context
from src.scraper.login import login
from src.scraper.search import SearchResult, fetch_job_description, search_jobs
from src.applicator.apply import apply_to_job


async def run_pipeline() -> dict:
    settings = get_settings()
    init_db()
    run_log = create_run_log()
    stats = {"scraped": 0, "scored": 0, "applied": 0, "skipped": 0, "errors": 0}

    logger.info("=" * 60)
    logger.info(f"Pipeline started — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    logger.info(f"Keywords: {settings.keywords_list}")
    logger.info(f"Match threshold: {settings.match_threshold}")

    try:
        async with get_browser_context() as context:
            page = await login(context)

            # ── Phase 1: Scrape ───────────────────────────────────────────────
            all_results: list[SearchResult] = []
            for keyword in settings.keywords_list:
                results = await search_jobs(page, keyword)
                all_results.extend(results)

            # Deduplicate across keywords
            seen_ids: set[str] = set()
            unique_results = []
            for r in all_results:
                if r.job_id not in seen_ids:
                    seen_ids.add(r.job_id)
                    unique_results.append(r)

            stats["scraped"] = len(unique_results)
            logger.info(f"Scraped {len(unique_results)} unique jobs")

            # ── Phase 2: Filter & Score ───────────────────────────────────────
            easy_count = sum(1 for r in unique_results if r.is_easy_apply)
            logger.info(
                f"Easy/Quick Apply: {easy_count}/{len(unique_results)} jobs. "
                f"EASY_APPLY_ONLY={settings.easy_apply_only}"
            )

            jobs_to_apply: list[Job] = []
            filtered_easy = 0
            for result in unique_results:
                if already_applied(result.job_id):
                    logger.debug(f"Already applied: {result.job_id}")
                    continue

                if result.company.lower() in settings.skip_companies_set:
                    logger.debug(f"Skipping company: {result.company}")
                    continue

                if settings.easy_apply_only and not result.is_easy_apply:
                    filtered_easy += 1
                    continue

                # Fetch JD if description is empty
                description = re.sub(r"<[^>]+>", " ", result.description or "")
                if not description.strip():
                    description = await fetch_job_description(page, result.url)

                # Score with keyword matcher (synchronous, no API)
                try:
                    match: MatchResult = score_job(
                        title=result.title,
                        company=result.company,
                        experience=result.experience,
                        salary=result.salary,
                        skills=result.skills,
                        description=description,
                    )
                    stats["scored"] += 1
                except Exception as e:
                    logger.warning(f"Scoring failed for {result.job_id}: {e}")
                    stats["errors"] += 1
                    continue

                # Persist job with score
                job = Job(
                    job_id=result.job_id,
                    title=result.title,
                    company=result.company,
                    location=result.location,
                    experience=result.experience,
                    salary=result.salary,
                    skills=result.skills,
                    description=description[:2000],
                    url=result.url,
                    posted_date=result.posted_date,
                    applicant_count=result.applicant_count,
                    is_easy_apply=result.is_easy_apply,
                    match_score=match.score,
                    match_breakdown=json.dumps({"matched": match.matched_skills, "missing": match.missing_skills}),
                    status=ApplicationStatus.PENDING,
                )
                job = upsert_job(job)

                apply, reason = should_apply(match)
                if apply:
                    jobs_to_apply.append(job)
                    logger.info(
                        f"[{match.score:.0f}%] APPLY → {result.title} @ {result.company}"
                    )
                else:
                    logger.info(f"[{match.score:.0f}%] SKIP  → {result.title} @ {result.company}: {reason}")
                    stats["skipped"] += 1

            if filtered_easy:
                logger.warning(
                    f"{filtered_easy} jobs skipped (not Quick/Easy Apply). "
                    f"Set EASY_APPLY_ONLY=false in .env to score and apply to all jobs."
                )

            # ── Phase 3: Apply ────────────────────────────────────────────────
            # Sort by score descending, cap at max_apply_per_run
            jobs_to_apply.sort(key=lambda j: j.match_score or 0, reverse=True)
            jobs_to_apply = jobs_to_apply[: settings.max_apply_per_run]

            logger.info(f"Applying to {len(jobs_to_apply)} jobs (cap={settings.max_apply_per_run})")
            for job in jobs_to_apply:
                result_apply = await apply_to_job(page, job)
                if result_apply.success:
                    stats["applied"] += 1
                else:
                    stats["skipped"] += 1
                await asyncio.sleep(2)  # polite delay between applications

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        stats["errors"] += 1
        update_run_log(run_log.id, error=str(e))

    update_run_log(
        run_log.id,
        jobs_scraped=stats["scraped"],
        jobs_scored=stats["scored"],
        jobs_applied=stats["applied"],
        jobs_skipped=stats["skipped"],
    )

    logger.info(
        f"Pipeline done — scraped={stats['scraped']} scored={stats['scored']} "
        f"applied={stats['applied']} skipped={stats['skipped']} errors={stats['errors']}"
    )
    return stats
