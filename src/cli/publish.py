"""
Publishing CLI commands.
  anticorrupt publish preview   — preview formatted output
  anticorrupt publish send      — publish to a platform
  anticorrupt publish schedule  — schedule a post

Phase 3 — placeholder implementation.
"""

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Publish approved content to social platforms")
console = Console()


def _phase3_notice(feature: str) -> None:
    console.print(
        Panel(
            f"[yellow]⚙ Phase 3 — [bold]{feature}[/bold] not yet implemented[/yellow]\n\n"
            "Publishing will be available in Phase 3.\n"
            "It will support Instagram and X/Twitter with scheduling.",
            title="Publishing",
            border_style="yellow",
        )
    )


@app.command()
def preview(
    draft_id: str = typer.Argument(..., help="Draft ID to preview"),
    platform: str = typer.Option("instagram", "--platform", "-p", help="Platform format"),
) -> None:
    """Preview a draft formatted for a specific platform."""
    _phase3_notice(f"Preview ({platform}): {draft_id}")


@app.command()
def send(
    draft_id: str = typer.Argument(..., help="Draft ID to publish"),
    platform: str = typer.Option(..., "--platform", "-p", help="Platform: instagram | twitter"),
) -> None:
    """Publish an approved draft to a social platform."""
    _phase3_notice(f"Send ({platform}): {draft_id}")


@app.command()
def schedule(
    draft_id: str = typer.Argument(..., help="Draft ID to schedule"),
    time: str = typer.Option(..., "--time", "-t", help="ISO datetime (e.g., 2026-02-24T10:00)"),
    platform: str = typer.Option("instagram", "--platform", "-p"),
) -> None:
    """Schedule a draft to be published at a specific time."""
    _phase3_notice(f"Schedule ({platform}) at {time}: {draft_id}")
