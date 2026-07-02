from __future__ import annotations

from datetime import datetime

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core.database import get_recent_runs, get_stats, get_session
from src.core.models import ApplicationStatus, Job
from sqlmodel import select

console = Console()


def show_dashboard() -> None:
    console.clear()
    console.rule("[bold cyan]Naukri Job Bot — Dashboard[/bold cyan]")

    stats = get_stats()
    _render_stats(stats)
    _render_recent_applications()
    _render_run_history()


def _render_stats(stats: dict) -> None:
    panels = [
        Panel(f"[bold green]{stats['applied']}[/bold green]", title="Applied", border_style="green"),
        Panel(f"[bold yellow]{stats['pending']}[/bold yellow]", title="Pending", border_style="yellow"),
        Panel(f"[bold red]{stats['skipped']}[/bold red]", title="Skipped", border_style="red"),
        Panel(f"[bold blue]{stats['total']}[/bold blue]", title="Total Seen", border_style="blue"),
    ]
    console.print(Columns(panels))


def _render_recent_applications() -> None:
    with get_session() as session:
        jobs = list(
            session.exec(
                select(Job)
                .where(Job.status == ApplicationStatus.APPLIED)
                .order_by(Job.applied_at.desc())  # type: ignore[attr-defined]
                .limit(15)
            ).all()
        )

    table = Table(title="Recent Applications", box=box.ROUNDED, show_lines=True)
    table.add_column("Company", style="cyan", min_width=20)
    table.add_column("Role", style="white", min_width=30)
    table.add_column("Score", justify="right", style="green", min_width=6)
    table.add_column("Applied At", style="dim", min_width=16)
    table.add_column("Location", style="dim")

    for job in jobs:
        score_str = f"{job.match_score:.0f}%" if job.match_score else "—"
        applied_str = job.applied_at.strftime("%d %b %H:%M") if job.applied_at else "—"
        table.add_row(job.company, job.title, score_str, applied_str, job.location)

    if not jobs:
        table.add_row("—", "No applications yet", "—", "—", "—")
    console.print(table)


def _render_run_history() -> None:
    runs = get_recent_runs(limit=5)
    table = Table(title="Recent Runs", box=box.SIMPLE_HEAVY)
    table.add_column("Started", style="dim")
    table.add_column("Scraped", justify="right")
    table.add_column("Scored", justify="right")
    table.add_column("Applied", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="yellow")
    table.add_column("Status")

    for run in runs:
        started = run.started_at.strftime("%d %b %H:%M")
        status = "[red]Error[/red]" if run.error else "[green]OK[/green]"
        table.add_row(
            started,
            str(run.jobs_scraped),
            str(run.jobs_scored),
            str(run.jobs_applied),
            str(run.jobs_skipped),
            status,
        )

    if not runs:
        table.add_row("—", "—", "—", "—", "—", "Never run")
    console.print(table)


def show_top_pending(n: int = 20) -> None:
    with get_session() as session:
        jobs = list(
            session.exec(
                select(Job)
                .where(Job.status == ApplicationStatus.PENDING)
                .order_by(Job.match_score.desc())  # type: ignore[attr-defined]
                .limit(n)
            ).all()
        )

    table = Table(title=f"Top {n} Pending Jobs by Match Score", box=box.ROUNDED)
    table.add_column("Score", justify="right", style="green")
    table.add_column("Company", style="cyan")
    table.add_column("Role", style="white")
    table.add_column("Exp")
    table.add_column("Easy Apply")
    table.add_column("URL", style="dim")

    for job in jobs:
        score_str = f"{job.match_score:.0f}%" if job.match_score else "?"
        easy = "✓" if job.is_easy_apply else "✗"
        table.add_row(score_str, job.company, job.title, job.experience, easy, job.url[:60])

    console.print(table)


def export_to_excel(output_path: str = "data/applications.xlsx") -> None:
    import pandas as pd
    with get_session() as session:
        jobs = list(session.exec(select(Job)).all())

    rows = [
        {
            "Company": j.company,
            "Role": j.title,
            "Score": j.match_score,
            "Status": j.status.value,
            "Location": j.location,
            "Experience": j.experience,
            "Salary": j.salary,
            "Easy Apply": j.is_easy_apply,
            "Applied At": j.applied_at,
            "URL": j.url,
            "Skip Reason": j.skip_reason,
        }
        for j in jobs
    ]
    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False)
    console.print(f"[green]Exported {len(rows)} jobs to {output_path}[/green]")
