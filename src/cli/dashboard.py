"""
Dashboard command — quick overview of the project state.
  anticorrupt dashboard
"""

from pathlib import Path
from typing import Optional

import typer
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from src.knowledge.graph import build_graph, get_graph_stats
from src.knowledge.loader import load_knowledge_base

console = Console()


def dashboard(
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d"),
) -> None:
    """Show a quick overview of the knowledge base and project status."""
    dir_path = data_dir or settings.data_dir

    console.print()
    console.print(
        Panel(
            "[bold white]🇧🇷 Anti-Corrupt — Plataforma de Explicação Política[/bold white]\n"
            "[dim]AI-Assisted Political & Institutional Explainer[/dim]",
            border_style="blue",
        )
    )

    try:
        kb = load_knowledge_base(dir_path)
        G = build_graph(kb)
        summary = kb.summary()
        graph_stats = get_graph_stats(G)

        # KB stats panel
        kb_lines = (
            f"[cyan]Instituições:[/cyan]   [bold]{summary['institutions']}[/bold]\n"
            f"[magenta]Figuras:[/magenta]        [bold]{summary['figures']}[/bold]\n"
            f"[yellow]Eventos:[/yellow]        [bold]{summary['events']}[/bold]\n"
            f"[blue]Relacionamentos:[/blue] [bold]{summary['relationships']}[/bold]\n"
            f"[green]Glossário:[/green]      [bold]{summary['glossary_terms']}[/bold]"
        )

        # Phase status panel
        phase_lines = (
            "[bold green]✓[/bold green] Phase 0 — Foundation (atual)\n"
            "[dim]○ Phase 1 — Content Pipeline[/dim]\n"
            "[dim]○ Phase 2 — Visual Generation[/dim]\n"
            "[dim]○ Phase 3 — Publishing[/dim]\n"
            "[dim]○ Phase 4 — Web Platform[/dim]"
        )

        console.print(
            Columns([
                Panel(kb_lines, title="📚 Knowledge Base", border_style="cyan", width=35),
                Panel(phase_lines, title="🚀 Project Phases", border_style="green", width=40),
            ])
        )

        # Most connected entities
        if graph_stats["top_connected"]:
            table = Table(
                title="🔗 Entidades mais conectadas",
                show_header=True,
                header_style="bold",
                width=75,
            )
            table.add_column("Entidade")
            table.add_column("Conexões", justify="right", style="bold yellow")
            for item in graph_stats["top_connected"][:5]:
                table.add_row(
                    f"{item['label']} [dim]({item['id']})[/dim]",
                    str(item["degree"]),
                )
            console.print(table)

    except Exception as e:
        console.print(f"[red]Erro ao carregar knowledge base:[/red] {e}")
        console.print("[dim]Execute: anticorrupt kb validate  para verificar os dados[/dim]")

    console.print()
    console.print(
        "[dim]Comandos disponíveis: [bold]kb validate[/bold] · [bold]kb search[/bold] · "
        "[bold]kb graph[/bold] · [bold]kb stats[/bold][/dim]\n"
    )
