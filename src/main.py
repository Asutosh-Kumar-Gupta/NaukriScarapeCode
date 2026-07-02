from __future__ import annotations

import asyncio

import typer
from loguru import logger
from rich.console import Console

from src.core.config import get_settings
from src.core.database import init_db
from src.core.logger import setup_logger

app = typer.Typer(name="naukribot", add_completion=False, help="AI-powered Naukri job application bot")
console = Console()


@app.command()
def run(
    once: bool = typer.Option(False, "--once", help="Run pipeline once and exit (no scheduler)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Score jobs but do not apply"),
):
    """Start the bot. Runs every N minutes by default."""
    setup_logger()
    settings = get_settings()
    init_db()

    if dry_run:
        console.print("[yellow]DRY RUN mode — will score but not apply[/yellow]")
        import os
        os.environ["MAX_APPLY_PER_RUN"] = "0"

    if once:
        console.print("[cyan]Running pipeline once...[/cyan]")
        from src.core.pipeline import run_pipeline
        stats = asyncio.run(run_pipeline())
        console.print(f"[green]Done: {stats}[/green]")
        return

    # Continuous mode with scheduler
    from src.core.scheduler import create_scheduler
    console.print(
        f"[bold green]Naukri Bot started[/bold green] — "
        f"running every [cyan]{settings.schedule_interval_minutes}[/cyan] minutes\n"
        f"Keywords: {settings.keywords_list}\n"
        f"Threshold: {settings.match_threshold}%\n"
        f"Press Ctrl+C to stop."
    )

    # Run immediately on start, then schedule
    scheduler = create_scheduler()

    async def _main():
        from src.core.pipeline import run_pipeline
        await run_pipeline()
        scheduler.start()
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            console.print("\n[yellow]Bot stopped.[/yellow]")

    asyncio.run(_main())


@app.command()
def dashboard():
    """Show the application dashboard."""
    from src.dashboard.display import show_dashboard
    show_dashboard()


@app.command()
def pending(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of jobs to show"),
):
    """Show top pending jobs by match score."""
    from src.dashboard.display import show_top_pending
    show_top_pending(limit)


@app.command()
def export(
    output: str = typer.Option("data/applications.xlsx", "--output", "-o"),
):
    """Export all jobs to Excel."""
    from src.dashboard.display import export_to_excel
    export_to_excel(output)


@app.command()
def score_one(url: str = typer.Argument(..., help="Naukri job URL to score")):
    """Fetch and score a single job URL against your profile."""
    async def _score():
        from src.core.config import get_settings
        from src.scraper.browser import get_browser_context
        from src.scraper.login import login
        from src.scraper.search import fetch_job_description
        from src.matcher.scorer import score_job, should_apply

        async with get_browser_context() as ctx:
            page = await login(ctx)
            desc = await fetch_job_description(page, url)
            if not desc:
                console.print("[red]Could not fetch job description[/red]")
                return
            match = score_job(
                title="Job from URL",
                company="",
                experience="",
                salary="",
                skills="",
                description=desc,
            )
            apply, reason = should_apply(match)
            console.print(f"\n[bold]Match Score:[/bold] {match.score:.0f}%")
            console.print(f"[bold]Breakdown:[/bold] {match.breakdown}")
            console.print(f"[bold]Recommendation:[/bold] {match.recommendation}")
            console.print(f"[bold]Decision:[/bold] {'[green]APPLY[/green]' if apply else '[red]SKIP[/red]'} — {reason}")
            console.print(f"[bold]Missing Skills:[/bold] {', '.join(match.missing_skills) or 'None'}")

    asyncio.run(_score())


@app.command()
def setup_login():
    """Open a visible browser and log in to Naukri via Google. Run this once before anything else."""
    import asyncio
    from pathlib import Path

    async def _do_login():
        from src.scraper.browser import get_browser_context
        from src.scraper.login import login, _SESSION_FILE, _delete_session

        # Always delete stale session so browser.py opens visibly
        _delete_session()

        async with get_browser_context(force_visible=True) as ctx:
            page = await login(ctx)
            console.print("\n[bold green]Login successful! Session saved.[/bold green]")
            console.print(f"Session stored at: {_SESSION_FILE}")
            console.print("You can now run: [cyan]python -m src.main run --once[/cyan]")

    asyncio.run(_do_login())


@app.command()
def debug_search(
    keyword: str = typer.Argument("Software Engineer", help="Keyword to search"),
):
    """Run a single search and print what was found (no apply). Saves HTML to logs/ if 0 results."""
    async def _debug():
        from src.scraper.browser import get_browser_context
        from src.scraper.login import login
        from src.scraper.search import search_jobs

        async with get_browser_context() as ctx:
            page = await login(ctx)
            results = await search_jobs(page, keyword)
            if not results:
                console.print(f"[red]0 jobs found for '{keyword}'. Check logs/ for debug HTML.[/red]")
                return
            console.print(f"\n[green]{len(results)} jobs found for '{keyword}':[/green]\n")
            for r in results[:10]:
                console.print(
                    f"  [cyan]{r.title}[/cyan] @ [yellow]{r.company}[/yellow]\n"
                    f"    {r.location} | {r.experience} | Easy Apply: {r.is_easy_apply}\n"
                    f"    {r.url}\n"
                )

    asyncio.run(_debug())


if __name__ == "__main__":
    app()
