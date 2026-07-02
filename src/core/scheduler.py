from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.core.config import get_settings
from src.core.pipeline import run_pipeline


def create_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_pipeline_job,
        trigger=IntervalTrigger(minutes=settings.schedule_interval_minutes),
        id="naukri_pipeline",
        name="Naukri Job Application Pipeline",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


async def _run_pipeline_job() -> None:
    try:
        await run_pipeline()
    except Exception as e:
        logger.error(f"Scheduled pipeline run failed: {e}", exc_info=True)
