# Naukri Job Bot

AI-powered bot that searches Naukri, scores jobs against your resume, and auto-applies to matching roles.

---

## How It Works

1. Opens a browser and logs you in to Naukri via Google
2. Searches for jobs matching your keywords and experience range
3. Scores each job against your resume using keyword matching
4. Auto-applies to jobs above your match threshold
5. Logs every application to a SQLite database

---

## Setup

### 1. Prerequisites

- Python 3.12+
- macOS / Linux

### 2. Install

```bash
git clone <repo>
cd naukriscraperbot
bash setup.sh
```

This creates a `.venv`, installs all dependencies, and installs the Playwright Chromium browser.

### 3. Configure

```bash
cp .env.example .env
```

Open `.env` and set your preferences:

```env
MATCH_THRESHOLD=50           # apply only if score >= this (0–100)
SEARCH_KEYWORDS=Senior Software Engineer,Backend Engineer,GenAI Engineer
SEARCH_LOCATION=Bengaluru
SEARCH_EXPERIENCE_MIN=4
SEARCH_EXPERIENCE_MAX=8
SEARCH_MAX_PAGES=5           # pages per keyword (20 jobs/page)
MAX_APPLY_PER_RUN=10         # safety cap per pipeline run
EASY_APPLY_ONLY=false        # true = only Quick Apply jobs
SCHEDULE_INTERVAL_MINUTES=20
HEADLESS=false               # keep false — needed for Google login + CDN bypass
```

### 4. Update Your Resume

Edit `resume/resume.json` with your real profile. The scorer compares your skills against job descriptions — accurate data = better matches.

Key fields to fill:

```json
{
  "name": "Your Name",
  "skills": { "languages": [...], "frameworks": [...], "ai_ml": [...] },
  "experience": [...],
  "preferred_roles": [...],
  "expected_salary_lpa": 35,
  "min_salary_lpa": 25
}
```

---

## Running

Activate the virtualenv first:

```bash
source .venv/bin/activate
```

### Commands

| Command | What it does |
|---|---|
| `python -m src.main run --once` | Run pipeline once and exit |
| `python -m src.main run` | Run continuously every N minutes |
| `python -m src.main run --dry-run` | Score jobs but do not apply |
| `python -m src.main dashboard` | Terminal dashboard — stats + recent applications |
| `python -m src.main pending` | Show top pending jobs by score |
| `python -m src.main export` | Export all data to `data/applications.xlsx` |
| `python -m src.main score-one <url>` | Score a single Naukri job URL |
| `python -m src.main debug-search "keyword"` | Test search without applying |
| `python -m src.main setup-login` | Force a fresh Google login |

### First Run

```bash
python -m src.main run --once
```

A browser window opens. Sign in with Google. Once you land on the Naukri home page the bot continues automatically — searches, scores, and applies.

### Continuous Mode

```bash
python -m src.main run
```

Runs immediately, then repeats every `SCHEDULE_INTERVAL_MINUTES`. Press `Ctrl+C` to stop.

---

## Project Structure

```
naukriscraperbot/
├── .env                    # your config (never commit)
├── resume/
│   └── resume.json         # your profile — edit this
├── src/
│   ├── main.py             # CLI entry point
│   ├── core/
│   │   ├── config.py       # settings from .env
│   │   ├── models.py       # database schema
│   │   ├── database.py     # SQLite helpers
│   │   ├── profile.py      # resume.json loader
│   │   ├── pipeline.py     # scrape → score → apply orchestrator
│   │   └── scheduler.py    # APScheduler (continuous mode)
│   ├── scraper/
│   │   ├── browser.py      # Playwright browser context
│   │   ├── login.py        # Google OAuth login
│   │   └── search.py       # job search + API interception
│   ├── matcher/
│   │   └── scorer.py       # keyword scoring engine
│   ├── applicator/
│   │   └── apply.py        # apply flow automation
│   └── dashboard/
│       └── display.py      # Rich terminal UI + Excel export
├── data/
│   └── naukribot.db        # SQLite — all jobs and applications
├── logs/                   # run logs + debug HTML
├── screenshots/            # screenshots taken after applying
└── requirements.txt
```

---

## Tuning the Score Threshold

`MATCH_THRESHOLD` in `.env` controls what gets applied to:

| Threshold | Effect |
|---|---|
| `20` | Apply to almost everything |
| `50` | Apply to reasonably relevant jobs |
| `70` | Apply only to strong matches |
| `85` | Apply only to near-perfect matches |

Start at `50`, check the dashboard after a run, and adjust based on what you see being applied vs skipped.

---

## Viewing Results

```bash
# Terminal dashboard
python -m src.main dashboard

# Excel export
python -m src.main export
open data/applications.xlsx
```

---

## Troubleshooting

**0 jobs found / Access Denied**
- Naukri's CDN blocks headless browsers. Keep `HEADLESS=false`.
- Check `logs/debug_*.html` to see what the page actually returned.

**Login keeps expiring**
- Run `python -m src.main setup-login` to get a fresh session.

**All jobs skipped**
- Lower `MATCH_THRESHOLD` in `.env`.
- Run `python -m src.main pending` to see scores.

**Apply button not found**
- Check `screenshots/` — the bot saves a screenshot when it can't find the button.
- Naukri's layout changes periodically; open the job URL manually to inspect.
