"""
Sources CLI — manage API cache and data refresh.

Commands:
  anticorrupt sources status             → Show cache age per source
  anticorrupt sources refresh            → Force-refresh all API caches
  anticorrupt sources refresh --source camara
  anticorrupt sources snapshot           → Export full cache to JSON dump
  anticorrupt sources import <file>      → Import a snapshot
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="sources",
    help="🗄️  Manage API data cache and source refresh",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _get_cache():
    from src.sources.cache import APICache
    return APICache()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status():
    """Show cache statistics — record count and age per source."""
    cache = _get_cache()
    stats = cache.stats()

    if not stats:
        console.print("[yellow]Cache is empty. Run [bold]sources refresh[/bold] to populate.[/yellow]")
        return

    table = Table(title="🗄️  API Cache Status", show_header=True)
    table.add_column("Fonte", style="bold cyan")
    table.add_column("Registros", justify="right")
    table.add_column("Mais antigo")
    table.add_column("Mais recente")

    for source, info in sorted(stats.items()):
        table.add_row(
            source,
            str(info["count"]),
            info["oldest"][:19],
            info["newest"][:19],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

@app.command()
def refresh(
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help="Source to refresh: camara | senado | all (default: all)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be refreshed without fetching"),
):
    """Force-refresh API cache from live sources."""
    sources_to_refresh = []

    if source is None or source == "all":
        sources_to_refresh = ["camara"]
    else:
        sources_to_refresh = [source]

    if dry_run:
        console.print(f"[dim]Dry run — would refresh: {', '.join(sources_to_refresh)}[/dim]")
        return

    results: dict[str, int] = {}

    if "camara" in sources_to_refresh:
        console.print("[cyan]Refreshing Câmara dos Deputados...[/cyan]")
        try:
            from src.sources.camara_api import CamaraAPI
            with CamaraAPI() as api:
                r = api.refresh_all()
                results.update({f"camara/{k}": v for k, v in r.items()})
        except Exception as exc:
            console.print(f"[red]Câmara refresh failed: {exc}[/red]")

    if results:
        table = Table(title="✅ Refresh completo", show_header=True)
        table.add_column("Endpoint")
        table.add_column("Registros", justify="right")
        for endpoint, count in results.items():
            table.add_row(endpoint, str(count))
        console.print(table)
    else:
        console.print("[yellow]No data was refreshed.[/yellow]")


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

@app.command()
def snapshot(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output .json.gz path"),
):
    """Export the full API cache to a compressed JSON snapshot for backup/portability."""
    cache = _get_cache()
    path = cache.export_snapshot(output_path=output)
    stats = cache.stats()
    total = sum(v["count"] for v in stats.values())
    console.print(Panel(
        f"[green]✓[/green] {total} registros exportados\n{path}",
        title="📦 Snapshot exportado",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# import-snapshot
# ---------------------------------------------------------------------------

@app.command(name="import-snapshot")
def import_snapshot(
    file: Path = typer.Argument(..., help="Path to a .json.gz snapshot file"),
):
    """Import a previously exported cache snapshot."""
    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    cache = _get_cache()
    count = cache.import_snapshot(file)
    console.print(Panel(
        f"[green]✓[/green] {count} registros importados de {file}",
        title="📥 Snapshot importado",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------

@app.command()
def invalidate(
    source: str = typer.Argument(..., help="Source key to invalidate (e.g. camara_deputados)"),
):
    """Remove all cached entries for a specific source, forcing a re-fetch on next use."""
    cache = _get_cache()
    deleted = cache.invalidate_source(source)
    console.print(f"[yellow]Invalidated {deleted} cached entries for source '{source}'[/yellow]")
