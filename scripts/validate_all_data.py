#!/usr/bin/env python3
"""
validate_all_data.py
Run a full validation of the knowledge base and print a detailed report.
Usage: uv run python scripts/validate_all_data.py
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from src.knowledge.loader import load_knowledge_base
from src.knowledge.validator import validate_knowledge_base

console = Console()


def main() -> None:
    data_dir = settings.data_dir

    console.print(f"\n[bold]📋 Validating knowledge base at:[/bold] {data_dir.resolve()}\n")

    report = validate_knowledge_base(data_dir)

    # Detailed results table
    table = Table(show_header=True, header_style="bold", width=100)
    table.add_column("File", style="dim", width=45)
    table.add_column("Status", width=10)
    table.add_column("Errors", justify="right", width=8)
    table.add_column("Warnings", justify="right", width=10)

    for result in report.results:
        if result.errors:
            status = "[red]✗ FAIL[/red]"
        elif result.warnings:
            status = "[yellow]⚠ WARN[/yellow]"
        else:
            status = "[green]✓ OK[/green]"
        table.add_row(
            result.file,
            status,
            str(len(result.errors)),
            str(len(result.warnings)),
        )

    console.print(table)

    # Error details
    if report.files_with_errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for result in report.files_with_errors:
            console.print(f"\n  [red]{result.file}[/red]")
            for err in result.errors:
                console.print(f"    [red]└─[/red] {err}")

    # Warning details
    if report.files_with_warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for result in report.files_with_warnings:
            console.print(f"\n  [yellow]{result.file}[/yellow]")
            for warn in result.warnings:
                console.print(f"    [yellow]└─[/yellow] {warn}")

    # Summary
    console.print()
    if report.is_valid:
        console.print(
            Panel(
                f"[bold green]✓ All {report.total_files_checked} files valid![/bold green]\n"
                f"Warnings: {report.total_warnings}",
                border_style="green",
            )
        )
        sys.exit(0)
    else:
        console.print(
            Panel(
                f"[bold red]✗ Validation failed[/bold red]\n"
                f"Files: {report.total_files_checked}  •  "
                f"Errors: {report.total_errors}  •  "
                f"Warnings: {report.total_warnings}",
                border_style="red",
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
