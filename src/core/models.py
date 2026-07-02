from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
    ALREADY_APPLIED = "already_applied"


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True)       # Naukri internal job ID
    title: str
    company: str
    location: str
    experience: str = ""
    salary: str = ""
    skills: str = ""                                   # comma-separated
    description: str = ""
    url: str
    posted_date: str = ""
    applicant_count: str = ""
    is_easy_apply: bool = False

    match_score: Optional[float] = None
    match_breakdown: str = ""                          # JSON string

    status: ApplicationStatus = ApplicationStatus.PENDING
    applied_at: Optional[datetime] = None
    skip_reason: str = ""
    screenshot_path: str = ""

    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RunLog(SQLModel, table=True):
    __tablename__ = "run_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    jobs_scraped: int = 0
    jobs_scored: int = 0
    jobs_applied: int = 0
    jobs_skipped: int = 0
    error: str = ""
