"""
Main CLI entry point.
Usage: uv run anticorrupt [COMMAND]
"""

import typer
from rich.console import Console

from src.cli.dashboard import dashboard
from src.cli.generate import app as generate_app
from src.cli.generate import news_app
from src.cli.knowledge import app as kb_app
from src.cli.publish import app as publish_app
from src.cli.review import app as review_app

app = typer.Typer(
    name="anticorrupt",
    help="🇧🇷 AI-Assisted Political & Institutional Explainer Platform",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

console = Console()

# Register sub-apps
app.add_typer(kb_app, name="kb", help="📚 Knowledge base — validate, search, explore")
app.add_typer(generate_app, name="generate", help="🤖 Generate content with AI")
app.add_typer(news_app, name="news", help="📰 News ingestion — scan feeds, summarize")
app.add_typer(review_app, name="review", help="✍️  Review and approve drafts")
app.add_typer(publish_app, name="publish", help="📤 Publish to Instagram and X")

# Register top-level commands
app.command(name="dashboard")(dashboard)


if __name__ == "__main__":
    app()
