"""
Publishing CLI commands.

  anticorrupt publish preview   <draft-id>              — preview formatted output
  anticorrupt publish send      <draft-id> --platform … — publish now (or --dry-run)
  anticorrupt publish schedule  <draft-id> --time …     — add to schedule queue
  anticorrupt publish queue     [--platform …]          — list scheduled posts
  anticorrupt publish run-due   [--dry-run]             — execute all due posts
  anticorrupt publish analytics <draft-id>              — show post metrics
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from src.content.models import ContentStatus, Platform
from src.content.storage import DraftStore
from src.publish.analytics import AnalyticsStore
from src.publish.scheduler import PostScheduler, ScheduledPost

console = Console()
app = typer.Typer(help="Publish approved content to social platforms.")

_SCHED_DB = Path("output/schedule.db")
_ANALYTICS_DB = Path("output/analytics.db")
_DRAFTS_DB = Path("output/drafts.db")

_STATUS_EMOJI = {
    "pending": "⏳",
    "running": "⚙️ ",
    "done": "✅",
    "failed": "❌",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_draft(draft_id: str):  # type: ignore[return]
    store = DraftStore(_DRAFTS_DB)
    draft = store.get(draft_id)
    if draft is None:
        rprint(f"[red]Draft not found:[/red] {draft_id}")
        raise typer.Exit(1)
    return draft


def _format_dt(value: Optional[dt.datetime]) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y %H:%M")


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


@app.command()
def preview(
    draft_id: str = typer.Argument(..., help="Draft ID to preview"),
    platform: str = typer.Option(
        "instagram",
        "--platform",
        "-p",
        help="Platform format: instagram | twitter",
    ),
) -> None:
    """Preview a draft's formatted output for a specific platform."""
    draft = _get_draft(draft_id)

    content = draft.formatted or draft.body
    status_color = {"approved": "green", "pending_review": "yellow"}.get(
        draft.status.value, "white"
    )

    console.print(
        Panel(
            content,
            title=f"[bold]{draft.title}[/bold]  [{status_color}][{draft.status.value}][/{status_color}]",
            subtitle=f"[dim]{draft.content_type.value} · {platform} · {draft.word_count} words[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    if draft.status != ContentStatus.APPROVED:
        rprint(
            f"\n[yellow]⚠  Draft status is [bold]{draft.status.value}[/bold] — "
            "only approved drafts can be published.[/yellow]"
        )


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


@app.command()
def send(
    draft_id: str = typer.Argument(..., help="Draft ID to publish"),
    platform: str = typer.Option(
        ..., "--platform", "-p", help="Platform: instagram | twitter"
    ),
    image_url: Optional[list[str]] = typer.Option(
        None,
        "--image-url",
        help="Public image URL to attach (Instagram; repeat for carousel).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without posting."),
) -> None:
    """Publish an approved draft to a social platform."""
    draft = _get_draft(draft_id)

    if draft.status != ContentStatus.APPROVED:
        rprint(
            f"[red]Cannot publish:[/red] draft is [bold]{draft.status.value}[/bold]. "
            "Approve it first with [cyan]anticorrupt review approve[/cyan]."
        )
        raise typer.Exit(1)

    caption = draft.formatted or draft.body

    if dry_run:
        console.print(
            Panel(
                f"[bold]Platform:[/bold] {platform}\n"
                f"[bold]Images:[/bold]  {len(image_url or [])} URL(s)\n\n"
                + (caption[:500] + ("…" if len(caption) > 500 else "")),
                title="[yellow]DRY RUN — publish preview[/yellow]",
                border_style="yellow",
            )
        )
        rprint("[dim]No request sent.[/dim]")
        return

    post_id: str

    if platform == "instagram":
        if not image_url:
            rprint(
                "[red]Instagram requires at least one [bold]--image-url[/bold].[/red]\n"
                "[dim]Tip: render images first with [cyan]anticorrupt visuals carousel "
                f"{draft_id}[/cyan], host them, then pass the URLs here.[/dim]"
            )
            raise typer.Exit(1)

        from src.publish.instagram import InstagramClient, InstagramError

        with console.status("[bold]Publishing to Instagram…"):
            try:
                client = InstagramClient()
                if len(image_url) == 1:
                    post_id = client.post_image(image_url[0], caption)
                else:
                    post_id = client.post_carousel(image_url, caption)
            except InstagramError as exc:
                rprint(f"[red]Instagram error:[/red] {exc}")
                raise typer.Exit(1)

    elif platform == "twitter":
        from src.publish.twitter import TwitterClient, TwitterError

        images_dir = settings.images_dir / draft_id
        media: list[Path] = []
        if images_dir.exists():
            media = sorted(images_dir.glob("*.png"))[:4]

        with console.status("[bold]Publishing to X/Twitter…"):
            try:
                client = TwitterClient()
                result = client.post_tweet(caption[:280], media_paths=media or None)
                post_id = result.tweet_id
            except TwitterError as exc:
                rprint(f"[red]Twitter error:[/red] {exc}")
                raise typer.Exit(1)

    else:
        rprint(f"[red]Unsupported platform:[/red] {platform!r}. Use instagram or twitter.")
        raise typer.Exit(1)

    store = DraftStore(_DRAFTS_DB)
    draft.mark_published(Platform(platform), post_id=post_id)
    store.save(draft)

    rprint(
        f"\n[green]✓ Published[/green] [bold]{draft.title}[/bold]\n"
        f"  Platform : {platform}\n"
        f"  Post ID  : [cyan]{post_id}[/cyan]"
    )


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


@app.command()
def schedule(
    draft_id: str = typer.Argument(..., help="Draft ID to schedule"),
    time: str = typer.Option(
        ...,
        "--time",
        "-t",
        help='ISO datetime in UTC, e.g. "2026-03-01T10:00"',
    ),
    platform: str = typer.Option(
        "instagram",
        "--platform",
        "-p",
        help="Platform: instagram | twitter",
    ),
    image_url: Optional[list[str]] = typer.Option(
        None,
        "--image-url",
        help="Public image URL(s) for Instagram.",
    ),
    caption: Optional[str] = typer.Option(
        None,
        "--caption",
        help="Caption override (defaults to draft.formatted).",
    ),
) -> None:
    """Schedule an approved draft for future publishing."""
    draft = _get_draft(draft_id)

    if draft.status != ContentStatus.APPROVED:
        rprint(
            f"[red]Cannot schedule:[/red] draft is [bold]{draft.status.value}[/bold]. "
            "Approve it first."
        )
        raise typer.Exit(1)

    try:
        scheduled_at = dt.datetime.fromisoformat(time).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        rprint(
            f"[red]Invalid --time format:[/red] {time!r}. "
            "Use ISO 8601, e.g. 2026-03-01T10:00"
        )
        raise typer.Exit(1)

    if scheduled_at <= dt.datetime.now(dt.timezone.utc):
        rprint(
            "[yellow]Warning:[/yellow] scheduled time is in the past — "
            "post will run immediately on next [cyan]run-due[/cyan]."
        )

    scheduler = PostScheduler(_SCHED_DB)
    post = scheduler.add(
        ScheduledPost(
            draft_id=draft_id,
            platform=platform,
            scheduled_at=scheduled_at,
            image_urls=image_url or [],
            caption=caption or (draft.formatted or draft.body)[:2200],
        )
    )

    rprint(
        f"\n[green]✓ Scheduled[/green] [bold]{draft.title}[/bold]\n"
        f"  Post ID  : [cyan]{post.id}[/cyan]\n"
        f"  Platform : {platform}\n"
        f"  Time     : {_format_dt(scheduled_at)} UTC\n\n"
        "[dim]Run [cyan]anticorrupt publish run-due[/cyan] to execute due posts.[/dim]"
    )


# ---------------------------------------------------------------------------
# queue
# ---------------------------------------------------------------------------


@app.command()
def queue(
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p", help="Filter by platform."
    ),
    all_posts: bool = typer.Option(False, "--all", help="Show all posts (any status)."),
) -> None:
    """List scheduled posts."""
    scheduler = PostScheduler(_SCHED_DB)
    posts = scheduler.list_all() if all_posts else scheduler.list_pending()

    if platform:
        posts = [p for p in posts if p.platform == platform]

    if not posts:
        rprint("[yellow]No scheduled posts found.[/yellow]")
        stats = scheduler.stats()
        if stats:
            rprint(f"[dim]{stats}[/dim]")
        return

    table = Table(
        title=f"📅 Scheduled posts — {len(posts)} item(s)",
        show_lines=False,
    )
    table.add_column("ID", style="dim", width=10)
    table.add_column("Draft", style="cyan", width=10)
    table.add_column("Platform", width=12)
    table.add_column("Scheduled (UTC)", width=18)
    table.add_column("Status", width=10)
    table.add_column("Caption (preview)", width=45)

    for p in posts:
        emoji = _STATUS_EMOJI.get(p.status, "")
        table.add_row(
            p.id,
            p.draft_id,
            p.platform,
            _format_dt(p.scheduled_at),
            f"{emoji} {p.status}",
            (p.caption[:45] + "…") if len(p.caption) > 45 else p.caption,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# run-due
# ---------------------------------------------------------------------------


@app.command("run-due")
def run_due(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would run, without posting."
    ),
) -> None:
    """Execute all scheduled posts that are due (scheduled_at <= now)."""
    scheduler = PostScheduler(_SCHED_DB)
    due = scheduler.list_due()

    if not due:
        rprint("[green]✓ No posts due.[/green]")
        return

    rprint(f"[bold]{len(due)} post(s) due:[/bold]")

    for post in due:
        rprint(
            f"\n  [cyan]{post.id}[/cyan]  draft={post.draft_id}  "
            f"platform={post.platform}  scheduled={_format_dt(post.scheduled_at)}"
        )

        if dry_run:
            rprint("  [yellow][DRY RUN] would publish now[/yellow]")
            continue

        scheduler.update_status(post.id, "running")
        try:
            _dispatch_scheduled_post(post)
            scheduler.update_status(post.id, "done")
            rprint("  [green]✓ Done[/green]")
        except Exception as exc:
            scheduler.update_status(post.id, "failed", error=str(exc))
            rprint(f"  [red]✗ Failed:[/red] {exc}")


def _dispatch_scheduled_post(post: ScheduledPost) -> None:
    """Publish a due scheduled post to the appropriate platform."""
    store = DraftStore(_DRAFTS_DB)
    draft = store.get(post.draft_id)
    if draft is None:
        raise ValueError(f"Draft {post.draft_id!r} not found")

    caption = post.caption or draft.formatted or draft.body
    post_id: str

    if post.platform == "instagram":
        from src.publish.instagram import InstagramClient

        client = InstagramClient()
        if len(post.image_urls) == 1:
            post_id = client.post_image(post.image_urls[0], caption)
        elif len(post.image_urls) > 1:
            post_id = client.post_carousel(post.image_urls, caption)
        else:
            raise ValueError(
                "Instagram post requires at least one image URL in the schedule entry."
            )

    elif post.platform == "twitter":
        from src.publish.twitter import TwitterClient

        images_dir = settings.images_dir / post.draft_id
        media = sorted(images_dir.glob("*.png"))[:4] if images_dir.exists() else []

        client = TwitterClient()
        result = client.post_tweet(caption[:280], media_paths=media or None)
        post_id = result.tweet_id

    else:
        raise ValueError(f"Unsupported platform: {post.platform!r}")

    draft.mark_published(Platform(post.platform), post_id=post_id)
    store.save(draft)

    analytics = AnalyticsStore(_ANALYTICS_DB)
    analytics.store_batch(
        post_id=post_id,
        platform=post.platform,
        draft_id=post.draft_id,
        metrics={},
    )


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------


@app.command()
def analytics(
    draft_id: str = typer.Argument(..., help="Draft ID to show metrics for"),
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p", help="Filter by platform."
    ),
    fetch: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch fresh metrics from the platform API before displaying.",
    ),
) -> None:
    """Show post performance metrics for a published draft."""
    draft = _get_draft(draft_id)

    if not draft.publish_records:
        rprint(
            f"[yellow]Draft [bold]{draft_id}[/bold] has no publish records yet.[/yellow]"
        )
        raise typer.Exit(0)

    if fetch:
        _refresh_metrics(draft, platform)

    analytics_store = AnalyticsStore(_ANALYTICS_DB)
    rows = analytics_store.get_draft_metrics(draft_id)

    if platform:
        rows = [r for r in rows if r["platform"] == platform]

    if not rows:
        rprint(
            f"[yellow]No metrics stored for draft [bold]{draft_id}[/bold].[/yellow]\n"
            "[dim]Run with [cyan]--fetch[/cyan] to pull from the platform API.[/dim]"
        )
        return

    table = Table(
        title=f"📊 Analytics — [bold]{draft.title}[/bold]",
        show_lines=False,
    )
    table.add_column("Platform", style="cyan", width=12)
    table.add_column("Post ID", style="dim", width=22)
    table.add_column("Metric", width=20)
    table.add_column("Value", justify="right", width=12)
    table.add_column("Fetched", style="dim", width=18)

    for pub in draft.publish_records:
        pub_rows = [
            r
            for r in rows
            if r["post_id"] == (pub.post_id or "")
            and r["platform"] == pub.platform.value
        ]
        for r in pub_rows:
            table.add_row(
                r["platform"],
                r["post_id"],
                r["metric_name"],
                f"{r['metric_value']:,.0f}",
                r["fetched_at"][:16],
            )

    console.print(table)


def _refresh_metrics(draft: object, platform: Optional[str] = None) -> None:
    """Pull fresh metrics from platform APIs and store them."""
    analytics_store = AnalyticsStore(_ANALYTICS_DB)

    for pub in draft.publish_records:  # type: ignore[union-attr]
        if platform and pub.platform.value != platform:
            continue
        if pub.post_id is None:
            continue
        try:
            if pub.platform.value == "instagram":
                from src.publish.instagram import InstagramClient

                metrics = InstagramClient().get_media_insights(pub.post_id)
                analytics_store.store_batch(
                    pub.post_id, "instagram", draft.id, {k: float(v) for k, v in metrics.items()}  # type: ignore[union-attr]
                )
            elif pub.platform.value == "twitter":
                from src.publish.twitter import TwitterClient

                metrics = TwitterClient().get_tweet_metrics(pub.post_id)
                analytics_store.store_batch(
                    pub.post_id, "twitter", draft.id, {k: float(v) for k, v in metrics.items()}  # type: ignore[union-attr]
                )
            rprint(f"  [green]✓[/green] Fetched {pub.platform.value} metrics for {pub.post_id}")
        except Exception as exc:
            rprint(f"  [red]✗[/red] {pub.platform.value}: {exc}")
