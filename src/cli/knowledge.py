"""
Knowledge base CLI commands.
  anticorrupt kb validate   — validate all YAML files
  anticorrupt kb search     — search the knowledge base
  anticorrupt kb graph      — explore relationships for an entity
  anticorrupt kb stats      — show knowledge base statistics
"""

from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from config.settings import settings
from src.knowledge.graph import build_graph, get_entity_connections, get_graph_stats
from src.knowledge.loader import load_knowledge_base
from src.knowledge.search import get_total_results, search_knowledge_base
from src.knowledge.validator import validate_knowledge_base

app = typer.Typer(help="Knowledge base management commands")
console = Console()


@app.command()
def validate(
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d", help="Path to data directory"),
    show_warnings: bool = typer.Option(True, "--warnings/--no-warnings", help="Show warnings"),
) -> None:
    """Validate all YAML files in the knowledge base against their schemas."""
    dir_path = data_dir or settings.data_dir

    console.print(f"\n[bold]Validating knowledge base at:[/bold] {dir_path}\n")

    report = validate_knowledge_base(dir_path)

    # Print results
    for result in report.results:
        if result.errors:
            console.print(f"[red]✗[/red] {result.file}")
            for err in result.errors:
                console.print(f"  [red]  └─ {err}[/red]")
        elif result.warnings and show_warnings:
            console.print(f"[yellow]⚠[/yellow] {result.file}")
            for warn in result.warnings:
                console.print(f"  [yellow]  └─ {warn}[/yellow]")
        else:
            if not result.file.startswith("<"):
                console.print(f"[green]✓[/green] {result.file}")

    # Summary
    console.print()
    if report.is_valid:
        console.print(
            Panel(
                f"[bold green]✓ All files valid![/bold green]\n"
                f"Files checked: {report.total_files_checked}  •  "
                f"Warnings: {report.total_warnings}",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]✗ Validation failed[/bold red]\n"
                f"Files checked: {report.total_files_checked}  •  "
                f"Errors: {report.total_errors}  •  "
                f"Warnings: {report.total_warnings}",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d"),
    limit: int = typer.Option(5, "--limit", "-n", help="Results per category"),
) -> None:
    """Search the knowledge base across all entity types."""
    dir_path = data_dir or settings.data_dir
    kb = load_knowledge_base(dir_path)

    console.print(f"\n[bold]Searching for:[/bold] [cyan]{query}[/cyan]\n")

    results = search_knowledge_base(kb, query, limit=limit)
    total = get_total_results(results)

    if total == 0:
        console.print("[yellow]No results found.[/yellow]")
        return

    # Institutions
    if results["institutions"]:
        table = Table(title="🏛 Instituições", show_header=True, header_style="bold blue")
        table.add_column("ID", style="dim", width=20)
        table.add_column("Nome", width=30)
        table.add_column("Tipo")
        table.add_column("Descrição", width=50)
        for r in results["institutions"]:
            table.add_row(r["id"], r["name"], r["type"], r["description"])
        console.print(table)

    # Figures
    if results["figures"]:
        table = Table(title="👤 Figuras Públicas", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=25)
        table.add_column("Nome", width=35)
        table.add_column("Cargo Atual", width=40)
        for r in results["figures"]:
            table.add_row(r["id"], r["name"], r.get("current_role") or "—")
        console.print(table)

    # Events
    if results["events"]:
        table = Table(title="📅 Eventos", show_header=True, header_style="bold yellow")
        table.add_column("ID", style="dim", width=30)
        table.add_column("Título", width=40)
        table.add_column("Data", width=12)
        table.add_column("Resumo", width=60)
        for r in results["events"]:
            table.add_row(r["id"], r["title"], r["date"], r["summary"])
        console.print(table)

    # Glossary
    if results["glossary"]:
        table = Table(title="📖 Glossário", show_header=True, header_style="bold green")
        table.add_column("ID", style="dim", width=20)
        table.add_column("Termo", width=25)
        table.add_column("Definição", width=70)
        for r in results["glossary"]:
            table.add_row(r["id"], r["term_pt"], r["definition"])
        console.print(table)

    console.print(f"\n[dim]Total: {total} resultado(s) para '{query}'[/dim]\n")


@app.command()
def graph(
    entity: str = typer.Option(..., "--entity", "-e", help="Entity ID to explore"),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d"),
) -> None:
    """Explore the relationship graph for a given entity."""
    dir_path = data_dir or settings.data_dir
    kb = load_knowledge_base(dir_path)
    G = build_graph(kb)

    connections = get_entity_connections(G, entity)
    if "error" in connections:
        console.print(f"[red]{connections['error']}[/red]")
        raise typer.Exit(code=1)

    entity_data = connections["entity"]
    label = entity_data.get("label", entity)
    node_type = entity_data.get("node_type", "unknown")

    tree = Tree(
        f"[bold cyan]{label}[/bold cyan] [dim]({node_type} / {entity})[/dim]",
        guide_style="dim",
    )

    # Outgoing relationships
    if connections["outgoing"]:
        out_branch = tree.add("[bold green]→ Relacionamentos (saída)[/bold green]")
        for conn in connections["outgoing"]:
            rel = conn["relationship"]
            target_label = conn["entity"].get("label", conn["entity_id"])
            out_branch.add(
                f"[green]{rel['rel_type']}[/green] → [white]{target_label}[/white] "
                f"[dim]({conn['entity_id']})[/dim]\n"
                f"  [dim italic]{rel.get('description', '')}[/dim italic]"
            )

    # Incoming relationships
    if connections["incoming"]:
        in_branch = tree.add("[bold yellow]← Relacionamentos (entrada)[/bold yellow]")
        for conn in connections["incoming"]:
            rel = conn["relationship"]
            source_label = conn["entity"].get("label", conn["entity_id"])
            in_branch.add(
                f"[yellow]{rel['rel_type']}[/yellow] ← [white]{source_label}[/white] "
                f"[dim]({conn['entity_id']})[/dim]\n"
                f"  [dim italic]{rel.get('description', '')}[/dim italic]"
            )

    if not connections["outgoing"] and not connections["incoming"]:
        tree.add("[dim]Nenhum relacionamento encontrado[/dim]")

    console.print()
    console.print(tree)
    console.print(f"\n[dim]Grau total de conexões: {connections['degree']}[/dim]\n")


@app.command()
def stats(
    data_dir: Optional[Path] = typer.Option(None, "--data-dir", "-d"),
) -> None:
    """Show knowledge base and graph statistics."""
    dir_path = data_dir or settings.data_dir
    kb = load_knowledge_base(dir_path)
    G = build_graph(kb)

    summary = kb.summary()
    graph_stats = get_graph_stats(G)

    # KB Summary table
    kb_table = Table(title="📚 Knowledge Base", show_header=True, header_style="bold")
    kb_table.add_column("Tipo de Entidade", style="cyan")
    kb_table.add_column("Total", justify="right", style="bold")
    kb_table.add_row("Instituições", str(summary["institutions"]))
    kb_table.add_row("Figuras Públicas", str(summary["figures"]))
    kb_table.add_row("Eventos", str(summary["events"]))
    kb_table.add_row("Relacionamentos", str(summary["relationships"]))
    kb_table.add_row("Termos do Glossário", str(summary["glossary_terms"]))
    kb_table.add_section()
    kb_table.add_row("[bold]Total de Entidades[/bold]", f"[bold]{summary['total_entities']}[/bold]")
    console.print(kb_table)

    # Graph stats
    console.print()
    graph_table = Table(title="🕸 Grafo de Relacionamentos", show_header=True, header_style="bold")
    graph_table.add_column("Métrica", style="cyan")
    graph_table.add_column("Valor", justify="right", style="bold")
    graph_table.add_row("Total de nós", str(graph_stats["total_nodes"]))
    graph_table.add_row("Total de arestas", str(graph_stats["total_edges"]))
    graph_table.add_row("Grafo conectado", "✓" if graph_stats["is_connected"] else "✗")
    console.print(graph_table)

    # Top connected entities
    if graph_stats["top_connected"]:
        console.print()
        top_table = Table(title="🔗 Entidades Mais Conectadas", show_header=True, header_style="bold")
        top_table.add_column("ID", style="dim")
        top_table.add_column("Nome")
        top_table.add_column("Conexões", justify="right", style="bold yellow")
        for item in graph_stats["top_connected"]:
            top_table.add_row(item["id"], item["label"], str(item["degree"]))
        console.print(top_table)
