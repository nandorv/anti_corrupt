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

    # ── DB stats (history.db) ──────────────────────────────────────────────
    db_lines = "[dim]DB não encontrado — rode seed_eleicoes.py[/dim]"
    try:
        import os, json
        from src.history.store import HistoryStore
        db_path = Path(os.getenv("OUTPUT_DIR", "output")) / "history.db"
        store = HistoryStore(db_path)
        db_stats = store.stats()
        db = store._db

        # Break down politicians by source
        tse_count  = db.execute("SELECT COUNT(*) FROM politicians WHERE id LIKE 'tse:%'").fetchone()[0]
        csv_count  = db.execute("SELECT COUNT(*) FROM politicians WHERE id LIKE 'csv:%'").fetchone()[0]
        other_count = db_stats["politicians"] - tse_count - csv_count
        mag_count  = db.execute("SELECT COUNT(*) FROM politicians WHERE tags LIKE '%magistrado%'").fetchone()[0]

        db_lines = (
            f"[bold]{db_stats['politicians']:,}[/bold] políticos totais\n"
            f"  [cyan]TSE eleitos:[/cyan]   [bold]{tse_count:,}[/bold]\n"
            f"  [cyan]Magistrados:[/cyan]   [bold]{mag_count:,}[/bold]\n"
            f"  [cyan]CSV outros:[/cyan]    [bold]{csv_count - mag_count:,}[/bold]\n"
            + (f"  [dim]Wikidata/outro:[/dim] [bold]{other_count:,}[/bold]\n" if other_count else "")
            + f"[bold]{db_stats['election_results']:,}[/bold] resultados eleitorais\n"
        )
        if db_stats["votes"]:
            db_lines += f"[bold]{db_stats['votes']:,}[/bold] votos legislativos\n"
        else:
            db_lines += "[dim]Votos: não importados (history import-votes)[/dim]\n"
        if db_stats["expenses"]:
            db_lines += f"[bold]{db_stats['expenses']:,}[/bold] despesas CEAP"
        else:
            db_lines += "[dim]CEAP: não importado (history import-expenses)[/dim]"
    except Exception as e:
        db_lines = f"[dim]Erro ao ler DB: {e}[/dim]"

    # ── Phase status ───────────────────────────────────────────────────────
    phase_lines = (
        "[bold green]✓[/bold green] Phase 0  — Foundation\n"
        "[bold green]✓[/bold green] Phase 1  — Content Pipeline\n"
        "[bold green]✓[/bold green] Phase 2  — Visual Generation\n"
        "[bold green]✓[/bold green] Phase 3  — Publishing & Automation\n"
        "[bold green]✓[/bold green] Phase D  — History DB (SQLite)\n"
        "[bold green]✓[/bold green] Seed     — TSE CSV + Magistrados\n"
        "[dim]○ Phase 4  — Web Platform[/dim]\n"
        "[dim]○ Phase 5  — Scale & Monetize[/dim]"
    )

    # ── YAML Knowledge Base ────────────────────────────────────────────────
    try:
        kb = load_knowledge_base(dir_path)
        G = build_graph(kb)
        summary = kb.summary()
        graph_stats = get_graph_stats(G)

        kb_lines = (
            f"[cyan]Instituições:[/cyan]   [bold]{summary['institutions']}[/bold]\n"
            f"[magenta]Figuras:[/magenta]        [bold]{summary['figures']}[/bold]\n"
            f"[yellow]Eventos:[/yellow]        [bold]{summary['events']}[/bold]\n"
            f"[blue]Relacionamentos:[/blue] [bold]{summary['relationships']}[/bold]\n"
            f"[green]Glossário:[/green]      [bold]{summary['glossary_terms']}[/bold]"
        )
        kb_panel = Panel(kb_lines, title="📚 Knowledge Base (YAML)", border_style="cyan", width=35)

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
        kb_lines = f"[dim]Erro ao carregar knowledge base: {e}[/dim]"
        kb_panel = Panel(kb_lines, title="📚 Knowledge Base (YAML)", border_style="cyan", width=35)

    console.print(
        Columns([
            Panel(db_lines,     title="🗄️  History DB (SQLite)", border_style="yellow", width=38),
            Panel(kb_panel,     title="", border_style="none", width=37),
            Panel(phase_lines,  title="🚀 Project Phases",       border_style="green",  width=38),
        ])
    )

    console.print()
    console.print(
        "[dim]Comandos: [bold]history list[/bold] · [bold]history search <query>[/bold] · "
        "[bold]history show <id>[/bold] · [bold]history import-csv <file>[/bold] · "
        "[bold]kb validate[/bold][/dim]\n"
    )
