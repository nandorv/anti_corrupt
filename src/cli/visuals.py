"""
Visuals CLI — generate images from drafts and knowledge base data.

Commands:
  anticorrupt visuals carousel <draft-id>          → Instagram carousel PNGs
  anticorrupt visuals profile <figure-id>          → Profile card PNG
  anticorrupt visuals timeline <timeline-group>    → Timeline PNG
  anticorrupt visuals network <entity-id>          → Relationship network PNG
  anticorrupt visuals diagram <name>               → Institutional flowchart PNG
  anticorrupt visuals list-diagrams                → Show available predefined diagrams
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="visuals",
    help="🎨 Generate social media images",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_store():
    from src.content.storage import DraftStore
    from pathlib import Path
    return DraftStore(Path("output/drafts.db"))


def _load_kb():
    from src.knowledge.loader import load_knowledge_base
    from config.settings import Settings
    return load_knowledge_base(Settings().data_dir)


def _output_dir(sub: str) -> Path:
    p = Path("output/images") / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# carousel
# ---------------------------------------------------------------------------

@app.command()
def carousel(
    draft_id: str = typer.Argument(..., help="Draft ID (from review list)"),
    institution_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Institution type for accent color: judicial|legislative|executive"
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse slides but don't save images"),
):
    """Generate Instagram carousel PNG slides from an approved draft."""
    from src.visuals.carousel import parse_carousel_text, render_carousel_from_draft

    store = _load_store()
    draft = store.get(draft_id)

    if draft is None:
        console.print(f"[red]Draft {draft_id!r} not found.[/red]")
        raise typer.Exit(1)

    if not draft.formatted:
        console.print(
            f"[yellow]Draft {draft_id!r} has no formatted carousel text. "
            "Run [bold]generate format[/bold] first.[/yellow]"
        )
        raise typer.Exit(1)

    slides = parse_carousel_text(draft.formatted)
    if not slides:
        console.print("[red]Could not parse any slides from the draft's formatted content.[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Parsed {len(slides)} slides from draft {draft_id}[/cyan]")

    if dry_run:
        for s in slides:
            console.print(f"  Slide {s.index}: [bold]{s.title}[/bold] — {len(s.body)} chars")
        console.print("[dim]Dry run — no images saved.[/dim]")
        return

    out = output_dir or _output_dir(draft_id)
    paths = render_carousel_from_draft(
        formatted_text=draft.formatted,
        draft_id=draft_id,
        institution_type=institution_type,
        output_dir=out,
    )

    console.print(Panel(
        "\n".join(f"[green]✓[/green] {p}" for p in paths),
        title=f"🎨 Carousel — {len(paths)} slides",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------

@app.command()
def profile(
    figure_id: str = typer.Argument(..., help="Figure slug (e.g. alexandre-de-moraes)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output PNG path"),
):
    """Generate a profile card PNG for a public figure."""
    from src.visuals.profiles import render_profile_card

    kb = _load_kb()

    figure = kb.figures.get(figure_id)
    if figure is None:
        console.print(f"[red]Figure {figure_id!r} not found in knowledge base.[/red]")
        raise typer.Exit(1)

    out = output or Path("output/images") / f"profile_{figure_id}.png"
    path = render_profile_card(figure, output_path=out)

    console.print(Panel(
        f"[green]✓[/green] Saved: {path}",
        title=f"🧑 Profile: {figure.full_name}",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------

@app.command()
def timeline(
    group: str = typer.Argument(..., help="Timeline group slug (e.g. lava-jato)"),
    accent: Optional[str] = typer.Option(None, "--accent", help="Hex accent color, e.g. #1A365D"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Generate a horizontal timeline image from events in a timeline group."""
    from src.visuals.timelines import render_timeline as _render_timeline

    kb = _load_kb()

    events = [e for e in kb.events.values() if e.timeline_group == group]
    if not events:
        console.print(f"[red]No events found for timeline group {group!r}.[/red]")
        raise typer.Exit(1)

    title = group.replace("-", " ").title()
    out = output or Path("output/images") / f"timeline_{group}.png"
    path = _render_timeline(events, title=title, accent_color=accent, output_path=out)

    console.print(Panel(
        f"[green]✓[/green] {len(events)} events → {path}",
        title=f"📅 Timeline: {title}",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

@app.command()
def network(
    entity_id: str = typer.Argument(..., help="Entity slug to center the graph on"),
    depth: int = typer.Option(2, "--depth", "-d", help="Hops from center node"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Generate a relationship network diagram centered on an entity."""
    from src.visuals.network import render_network as _render_network
    from src.knowledge.graph import build_graph
    from src.knowledge.loader import load_knowledge_base
    from config.settings import Settings

    kb = load_knowledge_base(Settings().data_dir)
    G = build_graph(kb)

    if entity_id not in G:
        console.print(f"[red]Entity {entity_id!r} not found in knowledge graph.[/red]")
        raise typer.Exit(1)

    title = entity_id.replace("-", " ").title()
    out = output or Path("output/images") / f"network_{entity_id}.png"
    path = _render_network(G, center_node=entity_id, title=title, depth=depth, output_path=out)

    console.print(Panel(
        f"[green]✓[/green] Saved: {path}",
        title=f"🕸️  Network: {title}",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# diagram
# ---------------------------------------------------------------------------

@app.command()
def diagram(
    name: str = typer.Argument(..., help="Diagram name (use list-diagrams to see options)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Render a predefined institutional flowchart."""
    from src.visuals.diagrams import PREDEFINED_FLOWCHARTS, render_flowchart

    if name not in PREDEFINED_FLOWCHARTS:
        console.print(f"[red]Diagram {name!r} not found. Available:[/red]")
        for k in PREDEFINED_FLOWCHARTS:
            console.print(f"  • {k}")
        raise typer.Exit(1)

    flowchart = PREDEFINED_FLOWCHARTS[name]
    out = output or Path("output/images") / f"diagram_{name}.png"
    path = render_flowchart(flowchart, output_path=out)

    console.print(Panel(
        f"[green]✓[/green] {len(flowchart.steps)} steps → {path}",
        title=f"📊 Diagram: {flowchart.title}",
        border_style="green",
    ))


# ---------------------------------------------------------------------------
# list-diagrams
# ---------------------------------------------------------------------------

@app.command(name="list-diagrams")
def list_diagrams():
    """List all predefined institutional flowcharts."""
    from src.visuals.diagrams import PREDEFINED_FLOWCHARTS

    table = Table(title="📊 Diagramas disponíveis", show_header=True)
    table.add_column("Nome", style="bold cyan")
    table.add_column("Título")
    table.add_column("Passos", justify="right")

    for key, fc in PREDEFINED_FLOWCHARTS.items():
        table.add_row(key, fc.title, str(len(fc.steps)))

    console.print(table)
    console.print("\n[dim]Uso: anticorrupt visuals diagram <nome>[/dim]")
