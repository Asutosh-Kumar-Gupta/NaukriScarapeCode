from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.config import get_settings
from src.core.profile import UserProfile, get_profile


@dataclass
class MatchResult:
    score: float                 # 0–100
    matched_skills: list[str]
    missing_skills: list[str]
    recommendation: str          # APPLY / SKIP
    reasons: list[str]


# Synonym groups — any word in a group matches any other
_SYNONYMS: list[set[str]] = [
    {"ml", "machine learning"},
    {"ai", "artificial intelligence"},
    {"llm", "large language model", "large language models"},
    {"genai", "generative ai", "gen ai"},
    {"k8s", "kubernetes"},
    {"js", "javascript"},
    {"ts", "typescript"},
    {"pg", "postgres", "postgresql"},
    {"nosql", "no-sql"},
    {"aws", "amazon web services"},
    {"gcp", "google cloud"},
    {"ci/cd", "cicd", "ci cd"},
    {"rest", "restful", "rest api"},
    {"nlp", "natural language processing"},
    {"rag", "retrieval augmented generation"},
    {"fastapi", "fast api"},
    {"langchain", "lang chain"},
    {"langgraph", "lang graph"},
]

# Skills that are so common they carry less weight
_COMMON_SKILLS = {"python", "sql", "git", "rest", "docker", "aws", "html", "css"}


def _normalise(text: str) -> str:
    # Strip HTML tags before matching so <p>Python</p> → "python"
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse extra whitespace
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _skill_in_text(skill: str, text: str) -> bool:
    """Return True if skill or any synonym appears in text."""
    skill_lower = skill.lower()
    if skill_lower in text:
        return True
    for group in _SYNONYMS:
        if skill_lower in group:
            return any(syn in text for syn in group)
    return False


def score_job(
    title: str,
    company: str,
    experience: str,
    salary: str,
    skills: str,
    description: str,
) -> MatchResult:
    profile = get_profile()
    settings = get_settings()

    # Combine all available job text
    all_text = _normalise(f"{title} {skills} {description}")

    all_skills = profile.skills.all_skills()
    matched = [s for s in all_skills if _skill_in_text(s, all_text)]
    missing = [s for s in all_skills if s not in matched]

    # ── Score components ──────────────────────────────────────────────────────

    # 1. Coverage: what % of YOUR skills appear in the JD
    #    Weight rare/specialist skills more than common ones
    weighted_total = sum(2 if s.lower() not in _COMMON_SKILLS else 1 for s in all_skills)
    weighted_matched = sum(2 if s.lower() not in _COMMON_SKILLS else 1 for s in matched)
    coverage = (weighted_matched / weighted_total * 100) if weighted_total else 0

    # 2. Title relevance bonus (+15 if title matches a preferred role)
    title_lower = title.lower()
    role_bonus = 15 if any(r.lower() in title_lower for r in profile.preferred_roles) else 0

    # 3. Seniority match bonus (+10)
    senior_bonus = 10 if any(
        w in title_lower for w in ["senior", "staff", "lead", "principal", "manager"]
    ) else 0

    # 4. Domain bonus: AI/ML/GenAI roles get +10 for Asutosh's profile
    domain_bonus = 10 if any(
        w in all_text for w in ["genai", "llm", "langchain", "langgraph", "mlops", "generative"]
    ) else 0

    # 5. Hard negative: if JD explicitly requires skills we don't have at all
    #    and those are the primary skills listed → cap score
    hard_required = [s for s in missing if s.lower() in skills.lower()]
    hard_penalty = min(20, len(hard_required) * 5)

    score = min(100.0, coverage + role_bonus + senior_bonus + domain_bonus - hard_penalty)

    reasons: list[str] = [f"{len(matched)}/{len(all_skills)} skills matched"]
    if role_bonus:
        reasons.append("Title matches preferred roles")
    if senior_bonus:
        reasons.append("Seniority matches")
    if domain_bonus:
        reasons.append("GenAI/ML domain match")
    if hard_penalty:
        reasons.append(f"Missing required: {', '.join(hard_required[:3])}")

    recommendation = "APPLY" if score >= settings.match_threshold else "SKIP"

    return MatchResult(
        score=score,
        matched_skills=matched,
        missing_skills=missing,
        recommendation=recommendation,
        reasons=reasons,
    )


def should_apply(result: MatchResult) -> tuple[bool, str]:
    settings = get_settings()
    if result.score < settings.match_threshold:
        return False, f"Score {result.score:.0f}% < threshold {settings.match_threshold}%"
    return True, f"Score {result.score:.0f}% — {'; '.join(result.reasons)}"
