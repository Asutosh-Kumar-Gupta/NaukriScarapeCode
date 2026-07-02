from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from src.core.config import get_settings


class Experience(BaseModel):
    company: str
    role: str
    duration: str
    years: int
    highlights: list[str]


class Education(BaseModel):
    degree: str
    institution: str
    year: int


class Skills(BaseModel):
    languages: list[str] = []
    frameworks: list[str] = []
    ai_ml: list[str] = []
    cloud: list[str] = []
    devops: list[str] = []
    databases: list[str] = []
    architecture: list[str] = []

    def all_skills(self) -> list[str]:
        result = []
        for field in self.model_fields:
            result.extend(getattr(self, field))
        return list(set(result))


class UserProfile(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    total_experience_years: int
    current_role: str
    current_company: str
    expected_salary_lpa: int
    notice_period_days: int
    summary: str
    skills: Skills
    experience: list[Experience]
    education: list[Education]
    certifications: list[str] = []
    preferred_roles: list[str] = []
    preferred_locations: list[str] = []
    min_salary_lpa: int = 0

    def as_text(self) -> str:
        skills_text = ", ".join(self.skills.all_skills())
        exp_text = "\n".join(
            f"- {e.role} at {e.company} ({e.years} yrs): {'; '.join(e.highlights[:2])}"
            for e in self.experience
        )
        return f"""Name: {self.name}
Total Experience: {self.total_experience_years} years
Current Role: {self.current_role} at {self.current_company}
Location: {self.location}
Expected Salary: {self.expected_salary_lpa} LPA
Skills: {skills_text}

Experience:
{exp_text}

Summary: {self.summary}

Preferred Roles: {', '.join(self.preferred_roles)}
Preferred Locations: {', '.join(self.preferred_locations)}
"""


@lru_cache(maxsize=1)
def get_profile() -> UserProfile:
    settings = get_settings()
    path = Path(settings.resume_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Resume not found at {path}. Copy resume/resume.json and fill in your details."
        )
    with open(path) as f:
        data = json.load(f)
    return UserProfile(**data)
