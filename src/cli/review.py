"""CLI review commands — editorial queue management."""

from __future__ import annotations

from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.content.models import ContentStatus, ContentType
from src.content.queue import ReviewQueue
from src.content.storage import get_store

console = Console()
app = typer.Typer(help="Manage the editorial review queue.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command("list")
def review_list(
    status: str = typer.Option("all", "--status", "-s",
                                help="Filter: all | draft | pending | approved | published | rejected"),
    content_type: str = typer.Option("all", "--type", "-t",
                                      help="Filter: all | news_summary | institution_explainer | figure_profile | timeline"),
    limit: int = typer.Option(30, "--limit", "-n"),
) -> None:
    """List content drafts in the review queue."""
    queue = ReviewQueue(store=get_store())

    # Resolve filters
    status_filter = None
    if status != "all":
        try:
            status_filter = ContentStatus(status)
        except ValueError:
            rprint(f"[red]Status invalido: {status!r}[/red]")
            raise typer.Exit(1)

    type_filter = None
    if content_type != "all":
        try:
            type_filter = ContentType(content_type)
        except ValueError:
            rprint(f"[red]Tipo invalido: {content_type!r}[/red]")
            raise typer.Exit(1)

    drafts = queue.list_all(status=status_filter, content_type=type_filter, limit=limit)

    if not drafts:
        rprint("[yellow]Nenhum rascunho encontrado.[/yellow]")
        # Show queue stats
        stats = queue.stats()
        rprint(f"[dim]Total: {stats.total} | Pendentes: {stats.pending} | Aprovados: {stats.approved}[/dim]")
        return

    table = Table(title=f"📋 Fila editorial — {len(drafts)} rascunhos", show_lines=True)
    table.add_column("ID", style="bold", width=10)
    table.add_column("Tipo", style="cyan", width=22)
    table.add_column("Status", width=14)
    table.add_column("Titulo", width=50)
    table.add_column("Palavras", justify="right", width=8)
    table.add_column("Custo", justify="right", width=8)

    STATUS_COLORS = {
        "draft": "white",
        "pending_review": "yellow",
        "approved": "green",
        "published": "blue",
        "rejected": "red",
        "archived": "dim",
    }

    for d in drafts:
        color = STATUS_COLORS.get(d.status.value, "white")
        flag = " [red]🚩[/red]" if d.flagged else ""
        table.add_row(
            d.id,
            d.content_type.value,
            Text(d.status.value, style=color),
            d.title[:50] + flag,
            str(d.word_count),
            f"${d.estimated_cost_usd:.4f}",
        )

    console.print(table)

    stats = queue.stats()
    rprint(f"[dim]Total: {stats.total} | Pendentes: {stats.pending} | Aprovados: {stats.approved} | Publicados: {stats.published}[/dim]")
    rprint("\n[bold]Comandos:[/bold] review show <id> · review approve <id> · review reject <id> --note '...'")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@app.command("show")
def review_show(
    draft_id: str = typer.Argument(..., help="Draft ID"),
    full: bool = typer.Option(False, "--full", help="Show full body text"),
) -> None:
    """Show the full content of a draft."""
    queue = ReviewQueue(store=get_store())
    draft = queue.get(draft_id)
    if not draft:
        rprint(f"[red]Draft nao encontrado: {draft_id}[/red]")
        raise typer.Exit(1)

    # Header
    rprint(Panel(
        f"[bold]{draft.title}[/bold]\n"
        f"[dim]ID: {draft.id} | Tipo: {draft.content_type.value} | Status: {draft.status.value}[/dim]\n"
        f"[dim]Criado: {draft.created_at.strftime('%d/%m/%Y %H:%M')} | "
        f"Palavras: {draft.word_count} | Custo: ${draft.estimated_cost_usd:.4f}[/dim]",
        border_style="blue",
        title="📄 Rascunho",
    ))

    # Body
    body_text = draft.body if full else draft.body[:1200]
    if not full and len(draft.body) > 1200:
        body_text += "\n\n[dim]... (use --full para ver o texto completo)[/dim]"
    rprint(body_text)

    # Source
    if draft.source_url:
        rprint(f"\n[dim]Fonte: {draft.source_url}[/dim]")

    # Tags
    if draft.tags:
        rprint(f"[dim]Tags: {', '.join(draft.tags)}[/dim]")

    # Review notes
    if draft.review_notes:
        rprint("\n[bold]Notas editoriais:[/bold]")
        for note in draft.review_notes:
            rprint(f"  [{note.created_at.strftime('%d/%m %H:%M')}] [bold]{note.reviewer}[/bold]: {note.note}")

    # Formatted content
    if draft.formatted:
        rprint("\n[green]✓ Conteudo formatado disponivel[/green]")


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------

@app.command("submit")
def review_submit(
    draft_id: str = typer.Argument(..., help="Draft ID to submit for review"),
) -> None:
    """Submit a DRAFT to the review queue (PENDING_REVIEW)."""
    queue = ReviewQueue(store=get_store())
    try:
        draft = queue.submit_for_review(draft_id)
        rprint(f"[green]OK Submetido para revisao: [bold]{draft.id}[/bold][/green]")
    except (ValueError, Exception) as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

@app.command("approve")
def review_approve(
    draft_id: str = typer.Argument(..., help="Draft ID to approve"),
    note: str = typer.Option("", "--note", "-n", help="Optional approval note"),
    reviewer: str = typer.Option("editor", "--reviewer", "-r"),
) -> None:
    """Approve a draft for publishing."""
    queue = ReviewQueue(store=get_store())
    try:
        draft = queue.approve(draft_id, reviewer=reviewer, note=note)
        rprint(f"[green]OK Aprovado: [bold]{draft.id}[/bold] por {reviewer}[/green]")
        rprint("[bold]Proximo:[/bold] [cyan]anticorrupt generate format <id> --platform instagram[/cyan]")
    except (ValueError, Exception) as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------

@app.command("reject")
def review_reject(
    draft_id: str = typer.Argument(..., help="Draft ID to reject"),
    note: str = typer.Option(..., "--note", "-n", help="Reason for rejection (required)"),
    reviewer: str = typer.Option("editor", "--reviewer", "-r"),
) -> None:
    """Reject a draft with a mandatory note."""
    queue = ReviewQueue(store=get_store())
    try:
        draft = queue.reject(draft_id, reviewer=reviewer, note=note)
        rprint(f"[red]Rejeitado: [bold]{draft.id}[/bold] — {note}[/red]")
    except (ValueError, Exception) as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# flag / unflag
# ---------------------------------------------------------------------------

@app.command("flag")
def review_flag(
    draft_id: str = typer.Argument(..., help="Draft ID to flag"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for flagging"),
) -> None:
    """Flag a draft for special attention."""
    queue = ReviewQueue(store=get_store())
    try:
        draft = queue.flag(draft_id, reason=reason)
        rprint(f"[yellow]Flagged: [bold]{draft.id}[/bold] — {reason or 'sem motivo'}[/yellow]")
    except (ValueError, Exception) as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


@app.command("unflag")
def review_unflag(
    draft_id: str = typer.Argument(..., help="Draft ID to unflag"),
) -> None:
    """Remove flag from a draft."""
    queue = ReviewQueue(store=get_store())
    try:
        draft = queue.unflag(draft_id)
        rprint(f"[green]OK Unflagged: [bold]{draft.id}[/bold][/green]")
    except (ValueError, Exception) as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@app.command("stats")
def review_stats() -> None:
    """Show queue statistics."""
    queue = ReviewQueue(store=get_store())
    stats = queue.stats()

    table = Table(title="📊 Estatisticas da fila editorial", show_header=True)
    table.add_column("Status")
    table.add_column("Quantidade", justify="right")

    STATUS_COLORS = {
        "draft": "white",
        "pending_review": "yellow",
        "approved": "green",
        "published": "blue",
        "rejected": "red",
        "archived": "dim",
    }

    for status_val, count in sorted(stats.by_status.items()):
        color = STATUS_COLORS.get(status_val, "white")
        table.add_row(Text(status_val, style=color), str(count))

    table.add_row("[bold]Total[/bold]", f"[bold]{stats.total}[/bold]")
    console.print(table)

    if stats.flagged:
        rprint(f"[yellow]Flagged: {stats.flagged} rascunhos precisam de atencao[/yellow]")
