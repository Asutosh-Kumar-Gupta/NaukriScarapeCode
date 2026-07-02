from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from src.core.config import get_settings
from src.core.models import ApplicationStatus, Job, RunLog


def _get_engine():
    settings = get_settings()
    db_url = f"sqlite:///{settings.db_path}"
    return create_engine(db_url, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    engine = _get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(_get_engine())


# ── Job helpers ────────────────────────────────────────────────────────────────

def upsert_job(job: Job) -> Job:
    with get_session() as session:
        existing = session.exec(select(Job).where(Job.job_id == job.job_id)).first()
        if existing:
            # Only update fields that shouldn't overwrite manual status changes
            existing.match_score = job.match_score
            existing.match_breakdown = job.match_breakdown
            existing.is_easy_apply = job.is_easy_apply
            existing.skills = job.skills
            existing.description = job.description
            existing.updated_at = job.updated_at
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def job_exists(job_id: str) -> bool:
    with get_session() as session:
        return session.exec(select(Job).where(Job.job_id == job_id)).first() is not None


def already_applied(job_id: str) -> bool:
    with get_session() as session:
        job = session.exec(select(Job).where(Job.job_id == job_id)).first()
        return job is not None and job.status == ApplicationStatus.APPLIED


def mark_applied(job_id: str, screenshot_path: str = "") -> None:
    from datetime import datetime
    with get_session() as session:
        job = session.exec(select(Job).where(Job.job_id == job_id)).first()
        if job:
            job.status = ApplicationStatus.APPLIED
            job.applied_at = datetime.utcnow()
            job.screenshot_path = screenshot_path
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()


def mark_skipped(job_id: str, reason: str) -> None:
    from datetime import datetime
    with get_session() as session:
        job = session.exec(select(Job).where(Job.job_id == job_id)).first()
        if job:
            job.status = ApplicationStatus.SKIPPED
            job.skip_reason = reason
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()


def get_pending_jobs(limit: int = 50) -> list[Job]:
    with get_session() as session:
        return list(
            session.exec(
                select(Job)
                .where(Job.status == ApplicationStatus.PENDING)
                .where(Job.match_score >= get_settings().match_threshold)
                .order_by(Job.match_score.desc())  # type: ignore[attr-defined]
                .limit(limit)
            ).all()
        )


def get_stats() -> dict:
    with get_session() as session:
        all_jobs = session.exec(select(Job)).all()
        return {
            "total": len(all_jobs),
            "applied": sum(1 for j in all_jobs if j.status == ApplicationStatus.APPLIED),
            "skipped": sum(1 for j in all_jobs if j.status == ApplicationStatus.SKIPPED),
            "pending": sum(1 for j in all_jobs if j.status == ApplicationStatus.PENDING),
            "failed": sum(1 for j in all_jobs if j.status == ApplicationStatus.FAILED),
        }


# ── RunLog helpers ─────────────────────────────────────────────────────────────

def create_run_log() -> RunLog:
    with get_session() as session:
        log = RunLog()
        session.add(log)
        session.commit()
        session.refresh(log)
        return log


def update_run_log(log_id: int, **kwargs) -> None:
    from datetime import datetime
    with get_session() as session:
        log = session.get(RunLog, log_id)
        if log:
            for k, v in kwargs.items():
                setattr(log, k, v)
            if "finished_at" not in kwargs:
                log.finished_at = datetime.utcnow()
            session.add(log)
            session.commit()


def get_recent_runs(limit: int = 10) -> list[RunLog]:
    with get_session() as session:
        return list(
            session.exec(
                select(RunLog).order_by(RunLog.started_at.desc()).limit(limit)  # type: ignore[attr-defined]
            ).all()
        )
