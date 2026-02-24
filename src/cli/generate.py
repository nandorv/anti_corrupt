"""CLI generate commands — Phase 1 AI content pipeline."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.content.models import ContentDraft, ContentStatus, ContentType
from src.content.storage import get_store

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(help="Generate AI content from knowledge base and news feeds.")
news_app = typer.Typer(help="News ingestion and summarisation.")
app.add_typer(news_app, name="news")


# ---------------------------------------------------------------------------
# news scan
# ---------------------------------------------------------------------------

@news_app.command("scan")
def news_scan(
    sources: Optional[list[str]] = typer.Option(None, "--source", "-s"),
    limit: int = typer.Option(20, "--limit", "-n"),
    show_all: bool = typer.Option(False, "--all"),
) -> None:
    """Fetch latest articles from Brazilian news RSS feeds."""
    from src.sources.rss import scan_news, FEEDS

    language = None if show_all else "pt-BR"
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True, console=console) as progress:
        progress.add_task("Buscando feeds...", total=None)
        articles = scan_news(source_keys=sources or None, language_filter=language, max_per_feed=limit)

    if not articles:
        rprint("[yellow]Nenhum artigo encontrado.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"📰 {len(articles)} artigos encontrados", show_lines=False)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Fonte", style="cyan", width=22)
    table.add_column("Titulo", width=60)
    table.add_column("Data", style="dim", width=12)
    for art in articles[:50]:
        date_str = art.published_at.strftime("%d/%m %H:%M") if art.published_at else "—"
        table.add_row(art.id, art.source_name[:22], art.title[:60], date_str)
    console.print(table)
    rprint(f"\n[dim]Feeds: {', '.join(FEEDS.keys())}[/dim]")
    rprint("\n[bold]Proximo:[/bold] [cyan]anticorrupt generate news summarize[/cyan]")


# ---------------------------------------------------------------------------
# news summarize
# ---------------------------------------------------------------------------

@news_app.command("summarize")
def news_summarize(
    limit: int = typer.Option(5, "--limit", "-n"),
    sources: Optional[list[str]] = typer.Option(None, "--source", "-s"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    auto_submit: bool = typer.Option(False, "--submit"),
) -> None:
    """Fetch news and AI-summarize into draft content."""
    from src.sources.rss import scan_news
    from src.ai.summarizer import NewsSummarizer, ArticleInput
    from src.ai.client import get_client, MockLLMClient
    from src.knowledge.loader import load_knowledge_base
    from src.knowledge.search import search_knowledge_base
    from config.settings import settings

    rprint("[bold cyan]Buscando artigos...[/bold cyan]")
    articles = scan_news(source_keys=sources or None, max_per_feed=10)
    if not articles:
        rprint("[red]Nenhum artigo encontrado.[/red]")
        raise typer.Exit(1)

    top_articles = articles[:limit]
    rprint(f"[green]OK {len(articles)} artigos — processando os {len(top_articles)} primeiros[/green]")

    kb = load_knowledge_base(settings.data_dir)
    client = get_client(mock=dry_run)
    if isinstance(client, MockLLMClient):
        rprint("[yellow]AVISO: Modo mock (sem chamada real a API)[/yellow]")

    summarizer = NewsSummarizer(client=client)
    store = get_store()
    saved: list[ContentDraft] = []

    for art in top_articles:
        kb_results = search_knowledge_base(kb, art.title, limit=3)
        kb_ctx: list[str] = []
        for category in kb_results.values():
            for hit in category[:1]:
                name = getattr(hit, "name", "")
                desc = getattr(hit, "description", "")
                if name:
                    kb_ctx.append(f"- {name}: {desc[:100]}")
        kb_context = "\n".join(kb_ctx) or "Nenhum contexto adicional."

        article_input = ArticleInput(
            url=art.url,
            title=art.title,
            text=art.summary or art.title,
            source_name=art.source_name,
            tags=art.tags,
            kb_context=kb_context,
        )

        with Progress(SpinnerColumn(), TextColumn(f"Resumindo: {art.title[:50]}..."),
                      transient=True, console=console) as p:
            p.add_task("", total=None)
            result = summarizer.summarize(article_input)

        body_parts = []
        if result.what_happened:
            body_parts.append(f"**O que aconteceu**\n{result.what_happened}")
        if result.why_it_matters:
            body_parts.append(f"**Por que importa**\n{result.why_it_matters}")
        if result.institutional_context:
            body_parts.append(f"**Contexto institucional**\n{result.institutional_context}")
        body = "\n\n".join(body_parts) if body_parts else result.raw_text

        draft = ContentDraft(
            content_type=ContentType.NEWS_SUMMARY,
            status=ContentStatus.PENDING_REVIEW if auto_submit else ContentStatus.DRAFT,
            title=art.title[:200],
            body=body,
            source_url=art.url,
            source_name=art.source_name,
            source_article_id=art.id,
            tags=result.suggested_tags or art.tags,
            ai_model=result.response.model if result.response else None,
            ai_provider=result.response.provider if result.response else None,
            input_tokens=result.response.input_tokens if result.response else 0,
            output_tokens=result.response.output_tokens if result.response else 0,
            estimated_cost_usd=result.response.estimated_cost_usd if result.response else 0.0,
        )
        store.save(draft)
        saved.append(draft)
        icon = "OK" if result.is_complete else "~"
        rprint(f"  [{icon}] [bold]{draft.id}[/bold] — {art.title[:60]}")

    total_cost = sum(d.estimated_cost_usd for d in saved)
    total_tokens = sum(d.input_tokens + d.output_tokens for d in saved)
    rprint(f"\n[green]OK {len(saved)} rascunhos salvos[/green]")
    rprint(f"[dim]Tokens: {total_tokens:,} | Custo estimado: ${total_cost:.4f}[/dim]")
    rprint("\n[bold]Proximo:[/bold] [cyan]anticorrupt review list[/cyan]")


# ---------------------------------------------------------------------------
# generate explainer
# ---------------------------------------------------------------------------

@app.command("explainer")
def generate_explainer(
    institution: Optional[str] = typer.Option(None, "--institution", "-i"),
    topic: str = typer.Option("", "--topic", "-t"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    submit: bool = typer.Option(False, "--submit"),
) -> None:
    """Generate an educational explainer for an institution."""
    if not institution:
        rprint("[red]Use --institution <id>[/red]")
        raise typer.Exit(1)
    from config.settings import settings
    from src.knowledge.loader import load_knowledge_base
    from src.ai.client import get_client
    from src.ai.explainer import ContentExplainer

    kb = load_knowledge_base(settings.data_dir)
    client = get_client(mock=dry_run)
    with Progress(SpinnerColumn(), TextColumn(f"Gerando explainer: {institution}"),
                  transient=True, console=console) as p:
        p.add_task("", total=None)
        result = ContentExplainer(kb=kb, client=client).explain_institution(
            institution, specific_topic=topic
        )

    inst = kb.institutions.get(institution)
    title = f"Como funciona: {inst.name_common if inst else institution}"
    body_parts = []
    for section, value in [
        ("**O que e**", result.what_it_is),
        ("**Para que serve**", result.what_it_does),
        ("**Como funciona**", result.how_it_works),
        ("**Papel no sistema**", result.role_in_system),
        ("**Exemplo pratico**", result.practical_example),
    ]:
        if value:
            body_parts.append(f"{section}\n{value}")
    body = "\n\n".join(body_parts) if body_parts else result.raw_text

    draft = ContentDraft(
        content_type=ContentType.INSTITUTION_EXPLAINER,
        status=ContentStatus.PENDING_REVIEW if submit else ContentStatus.DRAFT,
        title=title, body=body,
        related_entity_ids=[institution],
        tags=["explainer", "instituicao", institution],
        ai_model=result.response.model if result.response else None,
        ai_provider=result.response.provider if result.response else None,
        input_tokens=result.response.input_tokens if result.response else 0,
        output_tokens=result.response.output_tokens if result.response else 0,
        estimated_cost_usd=result.response.estimated_cost_usd if result.response else 0.0,
    )
    get_store().save(draft)
    rprint(Panel(body[:800], title=f"[bold]{title}[/bold]", border_style="green"))
    rprint(f"[dim]Draft ID: [bold]{draft.id}[/bold] | Custo: ${draft.estimated_cost_usd:.4f}[/dim]")
    rprint("[bold]Proximo:[/bold] [cyan]anticorrupt review list[/cyan]")


# ---------------------------------------------------------------------------
# generate profile
# ---------------------------------------------------------------------------

@app.command("profile")
def generate_profile(
    figure: str = typer.Argument(..., help="Figure ID from knowledge base"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    submit: bool = typer.Option(False, "--submit"),
) -> None:
    """Generate a public figure profile."""
    from config.settings import settings
    from src.knowledge.loader import load_knowledge_base
    from src.ai.client import get_client
    from src.ai.explainer import ContentExplainer

    kb = load_knowledge_base(settings.data_dir)
    client = get_client(mock=dry_run)
    with Progress(SpinnerColumn(), TextColumn(f"Gerando perfil: {figure}"),
                  transient=True, console=console) as p:
        p.add_task("", total=None)
        result = ContentExplainer(kb=kb, client=client).generate_profile(figure)

    fig = kb.figures.get(figure)
    title = f"Perfil: {fig.full_name if fig else figure}"
    draft = ContentDraft(
        content_type=ContentType.FIGURE_PROFILE,
        status=ContentStatus.PENDING_REVIEW if submit else ContentStatus.DRAFT,
        title=title, body=result.raw_text,
        related_entity_ids=[figure],
        tags=["perfil", figure],
        ai_model=result.response.model if result.response else None,
        ai_provider=result.response.provider if result.response else None,
        input_tokens=result.response.input_tokens if result.response else 0,
        output_tokens=result.response.output_tokens if result.response else 0,
        estimated_cost_usd=result.response.estimated_cost_usd if result.response else 0.0,
    )
    get_store().save(draft)
    rprint(Panel(result.raw_text[:800], title=f"[bold]{title}[/bold]", border_style="blue"))
    rprint(f"[dim]Draft ID: [bold]{draft.id}[/bold][/dim]")


# ---------------------------------------------------------------------------
# generate timeline
# ---------------------------------------------------------------------------

@app.command("timeline")
def generate_timeline(
    group: str = typer.Argument(..., help="Timeline group name"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    submit: bool = typer.Option(False, "--submit"),
) -> None:
    """Generate a timeline narrative for an event group."""
    from config.settings import settings
    from src.knowledge.loader import load_knowledge_base
    from src.ai.client import get_client
    from src.ai.explainer import ContentExplainer

    kb = load_knowledge_base(settings.data_dir)
    client = get_client(mock=dry_run)
    with Progress(SpinnerColumn(), TextColumn(f"Gerando timeline: {group}"),
                  transient=True, console=console) as p:
        p.add_task("", total=None)
        result = ContentExplainer(kb=kb, client=client).generate_timeline(group)

    draft = ContentDraft(
        content_type=ContentType.TIMELINE,
        status=ContentStatus.PENDING_REVIEW if submit else ContentStatus.DRAFT,
        title=f"Timeline: {group}", body=result.raw_text,
        tags=["timeline", group],
        ai_model=result.response.model if result.response else None,
        ai_provider=result.response.provider if result.response else None,
        input_tokens=result.response.input_tokens if result.response else 0,
        output_tokens=result.response.output_tokens if result.response else 0,
        estimated_cost_usd=result.response.estimated_cost_usd if result.response else 0.0,
    )
    get_store().save(draft)
    rprint(Panel(result.raw_text[:800], title=f"[bold]Timeline: {group}[/bold]", border_style="magenta"))
    rprint(f"[dim]Draft ID: [bold]{draft.id}[/bold][/dim]")


# ---------------------------------------------------------------------------
# generate format
# ---------------------------------------------------------------------------

@app.command("format")
def format_draft(
    draft_id: str = typer.Argument(..., help="Draft ID to format"),
    platform: str = typer.Option("instagram", "--platform", "-p"),
    save: bool = typer.Option(True, "--save/--no-save"),
) -> None:
    """Format an approved draft for a specific platform."""
    from src.content.formatter import ContentFormatter
    from src.content.models import Platform

    store = get_store()
    draft = store.get(draft_id)
    if not draft:
        rprint(f"[red]Draft nao encontrado: {draft_id}[/red]")
        raise typer.Exit(1)

    try:
        platform_enum = Platform(platform.lower())
    except ValueError:
        rprint(f"[red]Plataforma invalida: {platform!r}. Validas: {[p.value for p in Platform]}[/red]")
        raise typer.Exit(1)

    formatted = ContentFormatter().format(draft, platform_enum)
    rprint(Panel(formatted, title=f"[bold]{platform.upper()} — {draft.title[:60]}[/bold]",
                 border_style="yellow"))
    if save:
        draft.formatted = formatted
        draft.touch()
        store.save(draft)
        rprint(f"[dim]Salvo no draft {draft_id}[/dim]")
