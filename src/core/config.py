from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Matching
    match_threshold: int = 85

    # Search
    search_keywords: str = "Senior Software Engineer,Backend Engineer,GenAI Engineer"
    search_location: str = "Bengaluru"
    search_experience_min: int = 5
    search_experience_max: int = 10
    search_max_pages: int = 10   # 10 pages × 20 jobs = up to 200 per keyword

    # Behaviour
    schedule_interval_minutes: int = 20
    max_apply_per_run: int = 10
    easy_apply_only: bool = True
    skip_companies: str = ""
    headless: bool = True

    # Paths
    db_path: str = "data/naukribot.db"
    resume_path: str = "resume/resume.json"
    log_path: str = "logs/naukribot.log"
    screenshots_path: str = "screenshots"

    # Derived helpers
    @property
    def keywords_list(self) -> list[str]:
        return [k.strip() for k in self.search_keywords.split(",") if k.strip()]

    @property
    def skip_companies_set(self) -> set[str]:
        return {c.strip().lower() for c in self.skip_companies.split(",") if c.strip()}

    def ensure_dirs(self) -> None:
        for p in [self.db_path, self.resume_path, self.log_path, self.screenshots_path]:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(self.screenshots_path).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
