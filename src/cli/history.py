"""
History CLI — build and query the historical political database.

Commands:
  stats              — row counts per table
  fetch-wiki         — pull data from Wikidata (no key required)
  enrich             — look up a person or topic on Wikipedia
  search             — full-text search across the database
  show               — display one record by ID
  import-votes       — import voting history from the Câmara API
  import-expenses    — import CEAP expenses from the Câmara API
  import-elections   — import electoral results from TSE
  export-yaml        — write a record as a YAML file to data/
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

app = typer.Typer(
    help="📜 Historical database — politicians, votes, elections, expenses",
    no_args_is_help=True,
)
console = Console()

_HISTORY_DB = Path(os.getenv("OUTPUT_DIR", "output")) / "history.db"
_DATA_DIR = Path("data")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store():
    from src.history.store import HistoryStore
    return HistoryStore(_HISTORY_DB)


def _fmt_list(items: list[str], max_items: int = 4) -> str:
    if not items:
        return "—"
    visible = items[:max_items]
    extra = len(items) - max_items
    result = ", ".join(visible)
    if extra > 0:
        result += f" (+{extra} more)"
    return result


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@app.command()
def stats() -> None:
    """Show record counts for every table in the historical database."""
    store = _store()
    counts = store.stats()

    table = Table(
        title="📜 Historical Database — Table Stats",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("Table", style="bold cyan")
    table.add_column("Records", justify="right", style="yellow")

    labels = {
        "politicians": "Politicians",
        "historical_events": "Historical Events",
        "votes": "Votes (individual)",
        "election_results": "Election Results",
        "expenses": "CEAP Expenses",
        "legislatures": "Legislatures",
    }
    total = 0
    for key, label in labels.items():
        count = counts.get(key, 0)
        total += count
        table.add_row(label, f"{count:,}")

    table.add_section()
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total:,}[/bold]")
    console.print(table)


# ---------------------------------------------------------------------------
# fetch-wiki
# ---------------------------------------------------------------------------


@app.command("fetch-wiki")
def fetch_wiki(
    type: str = typer.Option(
        "stf",
        "--type",
        "-t",
        help="What to fetch: stf | deputies | senators | presidents | governors | events | legislatures | all",
    ),
    limit: int = typer.Option(500, "--limit", "-n", help="Max records to fetch per category"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch but do not save to database"),
) -> None:
    """
    Fetch historical data from Wikidata and store it in the database.

    No API key required. Uses the public Wikidata SPARQL endpoint.
    Types: stf | deputies | senators | presidents | governors | events | legislatures | all
    """
    from src.sources.wikidata import WikidataClient

    valid_types = {"stf", "deputies", "senators", "presidents", "governors", "events", "legislatures", "all"}
    if type not in valid_types:
        console.print(f"[red]Unknown type '{type}'. Choose from: {', '.join(sorted(valid_types))}[/red]")
        raise typer.Exit(1)

    store = _store()
    client = WikidataClient()
    total_saved = 0

    fetch_map = {
        "stf": ("STF ministers", client.fetch_stf_ministers, None),
        "deputies": ("Federal Deputies", lambda: client.fetch_federal_deputies(limit=limit), None),
        "senators": ("Senators", lambda: client.fetch_senators(limit=limit), None),
        "presidents": ("Presidents", client.fetch_presidents, None),
        "governors": ("Governors", lambda: client.fetch_governors(limit=limit), None),
        "events": ("Political Events", lambda: client.fetch_political_events(limit=limit), None),
        "legislatures": ("Legislatures", client.fetch_legislatures, None),
    }

    to_run = list(fetch_map.keys()) if type == "all" else [type]

    for key in to_run:
        label, fn, _ = fetch_map[key]
        with console.status(f"Fetching {label} from Wikidata…"):
            try:
                records = fn()
            except Exception as exc:
                console.print(f"[red]  ✗ {label}: {exc}[/red]")
                continue

        if not dry_run:
            if key in ("stf", "deputies", "senators", "presidents", "governors"):
                saved = store.upsert_politicians(records)
            elif key == "events":
                saved = store.upsert_events(records)
            else:
                saved = store.upsert_legislatures(records)
        else:
            saved = len(records)

        total_saved += saved
        status = "[dim](dry-run)[/dim]" if dry_run else "saved"
        console.print(f"  [green]✓[/green] {label}: {saved:,} records {status}")

    client.__exit__()
    console.print(f"\n[bold green]Total: {total_saved:,} records{'  (dry-run — nothing written)' if dry_run else ' saved'}[/bold green]")


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------


@app.command()
def enrich(
    name: str = typer.Argument(..., help="Name or topic to look up on Wikipedia"),
    save: bool = typer.Option(False, "--save", help="Upsert the summary into the politicians table"),
) -> None:
    """
    Look up a person or topic on Wikipedia and display their summary.

    Use --save to store the Wikipedia summary back into the politicians table.
    """
    from src.sources.wikipedia import WikipediaClient

    with WikipediaClient() as wiki:
        with console.status(f"Looking up '{name}' on Wikipedia…"):
            summary = wiki.enrich_politician(name)

    if not summary:
        console.print(f"[yellow]No Wikipedia page found for '{name}'[/yellow]")
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]{summary.title}[/bold]\n\n{summary.extract}",
            title="📖 Wikipedia Summary",
            subtitle=summary.url,
            border_style="blue",
        )
    )

    if save:
        store = _store()
        from src.history.models import Politician
        # Try to find existing politician record to enrich
        results = store.search_politicians(name, limit=3)
        if results:
            pol = results[0]
            if not pol.summary:
                pol.summary = summary.extract[:1000]
            if not pol.sources:
                pol.sources = [summary.url]
            elif summary.url not in pol.sources:
                pol.sources.append(summary.url)
            store.upsert_politician(pol)
            console.print(f"[green]✓ Enriched existing record: {pol.id}[/green]")
        else:
            pol = Politician(name=name, summary=summary.extract[:1000], sources=[summary.url])
            store.upsert_politician(pol)
            console.print(f"[green]✓ Created new record: {pol.id}[/green]")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term"),
    type: str = typer.Option(
        "all",
        "--type",
        "-t",
        help="Record type: all | politician | event | vote | election | expense",
    ),
    limit: int = typer.Option(15, "--limit", "-n"),
) -> None:
    """
    Full-text search the historical database.
    Searches names, summaries, and titles depending on the type.
    """
    store = _store()

    if type in ("all", "politician"):
        politicians = store.search_politicians(query, limit=limit)
        if politicians:
            t = Table(title=f"Politicians matching '{query}'", box=box.SIMPLE)
            t.add_column("ID", style="dim")
            t.add_column("Name", style="bold")
            t.add_column("Party")
            t.add_column("State")
            t.add_column("Roles")
            for p in politicians:
                role_str = _fmt_list([r.role for r in p.roles], max_items=2)
                t.add_row(p.id, p.name, p.party or "—", p.state or "—", role_str)
            console.print(t)

    if type in ("all", "event"):
        events = store.search_events(query, limit=limit)
        if events:
            t = Table(title=f"Events matching '{query}'", box=box.SIMPLE)
            t.add_column("ID", style="dim")
            t.add_column("Title", style="bold")
            t.add_column("Date")
            t.add_column("Type")
            t.add_column("Summary", max_width=50)
            for e in events:
                t.add_row(e.id, e.title, e.date or "—", e.type, e.summary[:60] + "…" if len(e.summary) > 60 else e.summary)
            console.print(t)

    if type in ("all", "election"):
        results = store.search_election_results(candidate_name=query, limit=limit)
        if results:
            t = Table(title=f"Election results matching '{query}'", box=box.SIMPLE)
            t.add_column("Year", style="dim")
            t.add_column("Name", style="bold")
            t.add_column("Party")
            t.add_column("State")
            t.add_column("Position")
            t.add_column("Elected")
            for r in results:
                t.add_row(
                    str(r.year), r.candidate_name, r.party, r.state,
                    r.position, "✓" if r.elected else "✗"
                )
            console.print(t)

    if type == "all":
        total = (
            len(store.search_politicians(query, limit=1))
            + len(store.search_events(query, limit=1))
            + len(store.search_election_results(candidate_name=query, limit=1))
        )
        if total == 0:
            console.print(f"[yellow]No results found for '{query}'[/yellow]")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@app.command()
def show(
    record_id: str = typer.Argument(..., help="Record ID (e.g. wikidata:Q12345 or event:...)"),
) -> None:
    """Display the full details of a historical record by ID."""
    store = _store()

    # Try politicians first
    if record_id.startswith("wikidata:") or record_id.startswith("camara:") or record_id.startswith("pol:"):
        pol = store.get_politician(record_id)
        if pol:
            _show_politician(pol)
            return

    # Try events
    if record_id.startswith("event:"):
        event = store.get_event(record_id)
        if event:
            _show_event(event)
            return

    # Try both tables (bare ID)
    pol = store.get_politician(record_id)
    if pol:
        _show_politician(pol)
        return
    event = store.get_event(record_id)
    if event:
        _show_event(event)
        return

    console.print(f"[red]Record not found: {record_id}[/red]")
    raise typer.Exit(1)


def _show_politician(pol) -> None:
    lines = [
        f"[bold]{pol.name}[/bold]",
        f"ID: {pol.id}",
        f"Born: {pol.birth_date or '?'}  in  {pol.birth_place or '?'}",
        f"Party: {pol.party or '—'}  State: {pol.state or '—'}",
        "",
    ]
    if pol.summary:
        lines.append(pol.summary)
        lines.append("")
    if pol.roles:
        lines.append("[bold]Roles:[/bold]")
        for r in pol.roles:
            period = f"{r.start_date or '?'} → {r.end_date or 'present'}"
            lines.append(f"  • {r.role}  @{r.institution}  ({period})")
    if pol.tags:
        lines.append(f"\nTags: {', '.join(pol.tags)}")
    if pol.sources:
        lines.append(f"Sources: {', '.join(pol.sources[:3])}")
    console.print(Panel("\n".join(lines), title="👤 Politician", border_style="cyan"))


def _show_event(event) -> None:
    lines = [
        f"[bold]{event.title}[/bold]",
        f"ID: {event.id}",
        f"Date: {event.date or '?'} → {event.end_date or '—'}   Type: {event.type}",
        "",
        event.summary or "(no summary)",
    ]
    if event.detailed_description:
        lines.append("")
        lines.append(event.detailed_description)
    if event.significance:
        lines.append(f"\n[italic]Significance:[/italic] {event.significance}")
    if event.tags:
        lines.append(f"\nTags: {', '.join(event.tags)}")
    if event.sources:
        lines.append(f"Sources: {', '.join(event.sources[:3])}")
    console.print(Panel("\n".join(lines), title="📅 Historical Event", border_style="yellow"))


# ---------------------------------------------------------------------------
# import-votes
# ---------------------------------------------------------------------------


@app.command("import-votes")
def import_votes(
    deputy_id: int = typer.Option(..., "--deputy-id", "-d", help="Câmara deputy numeric ID"),
    start: Optional[str] = typer.Option(None, "--start", help="Start date YYYY-MM-DD"),
    end: Optional[str] = typer.Option(None, "--end", help="End date YYYY-MM-DD"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    Import a deputy's voting history from the Câmara API into the database.

    Example:
      history import-votes --deputy-id 73701 --start 2019-01-01
    """
    from src.sources.camara_api import CamaraAPI
    from src.history.models import Vote

    store = _store()
    api = CamaraAPI()

    with console.status(f"Fetching votes for deputy {deputy_id}…"):
        raw_votes = api.get_deputy_votes(deputy_id, start_date=start, end_date=end)

    console.print(f"  Fetched {len(raw_votes)} vote records from Câmara API")

    votes: list[Vote] = []
    for rv in raw_votes:
        try:
            vote_type = rv.get("tipoVoto", "").strip().upper()
            prop_info = rv.get("proposicao_") or {}
            prop_id = str(prop_info.get("id", ""))
            prop_title = prop_info.get("ementa") or prop_info.get("descricao") or ""
            prop_type = prop_info.get("siglaTipo") or None
            date_raw = rv.get("dataHoraVoto", "")
            date = date_raw[:10] if date_raw else ""
            session_id = str(rv.get("id", ""))

            if not vote_type or not date:
                continue

            votes.append(
                Vote(
                    deputy_camara_id=deputy_id,
                    deputy_id=f"camara:{deputy_id}",
                    deputy_name=rv.get("deputado_", {}).get("nome", f"Deputy {deputy_id}"),
                    proposition_id=f"camara:prop:{prop_id}" if prop_id else f"camara:session:{session_id}",
                    proposition_title=prop_title[:200],
                    proposition_type=prop_type,
                    vote=vote_type,
                    date=date,
                    session_id=session_id,
                    party=rv.get("deputado_", {}).get("siglaPartido"),
                    state=rv.get("deputado_", {}).get("siglaUf"),
                )
            )
        except Exception as exc:
            console.print(f"  [yellow]Skipping vote row: {exc}[/yellow]")

    if not dry_run:
        saved = store.upsert_votes(votes)
        console.print(f"[green]✓ Saved {saved:,} votes for deputy {deputy_id}[/green]")
    else:
        console.print(f"[dim]Dry-run: would save {len(votes):,} votes[/dim]")


# ---------------------------------------------------------------------------
# import-expenses
# ---------------------------------------------------------------------------


@app.command("import-expenses")
def import_expenses(
    deputy_id: int = typer.Option(..., "--deputy-id", "-d", help="Câmara deputy numeric ID"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Filter by year"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    Import CEAP expense records for a deputy from the Câmara API.

    Example:
      history import-expenses --deputy-id 73701 --year 2023
    """
    from src.sources.camara_api import CamaraAPI
    from src.history.models import Expense

    store = _store()
    api = CamaraAPI()

    # Get deputy name first
    with console.status(f"Fetching deputy {deputy_id} info…"):
        deputy_info = api.get_deputy(deputy_id)
    deputy_name = deputy_info.get("nomeCivil") or deputy_info.get("nome") or f"Deputy {deputy_id}"

    with console.status(f"Fetching CEAP expenses for {deputy_name}…"):
        raw_expenses = api.get_deputy_expenses(deputy_id, year=year)

    console.print(f"  Fetched {len(raw_expenses)} expense records")

    expenses: list[Expense] = []
    for re_ in raw_expenses:
        try:
            value = float(re_.get("valorDocumento") or re_.get("valorLiquido") or 0)
            if value <= 0:
                continue
            expense_year = int(re_.get("ano") or 0)
            expense_month = int(re_.get("mes") or 0)
            if expense_year == 0:
                continue

            expenses.append(
                Expense(
                    deputy_camara_id=deputy_id,
                    deputy_id=f"camara:{deputy_id}",
                    deputy_name=deputy_name,
                    year=expense_year,
                    month=expense_month,
                    category=(re_.get("tipoDespesa") or "OUTROS").strip(),
                    supplier=(re_.get("nomeFornecedor") or "").strip(),
                    supplier_cnpj_cpf=(re_.get("cnpjCpfFornecedor") or None),
                    value=value,
                    document_number=(re_.get("numDocumento") or None),
                    description=(re_.get("descricao") or None),
                )
            )
        except Exception as exc:
            console.print(f"  [yellow]Skipping expense row: {exc}[/yellow]")

    if not dry_run:
        saved = store.upsert_expenses(expenses)
        console.print(f"[green]✓ Saved {saved:,} expense records for {deputy_name}[/green]")
    else:
        console.print(f"[dim]Dry-run: would save {len(expenses):,} expense records[/dim]")


# ---------------------------------------------------------------------------
# import-elections
# ---------------------------------------------------------------------------


@app.command("import-elections")
def import_elections(
    year: int = typer.Option(..., "--year", "-y", help="Election year (e.g. 2022)"),
    state: Optional[str] = typer.Option(None, "--state", "-s", help="UF filter (e.g. SP)"),
    position: Optional[str] = typer.Option(
        None, "--position", "-p", help="Position filter substring (e.g. DEPUTADO FEDERAL)"
    ),
    limit: int = typer.Option(2000, "--limit", "-n", help="Max records to import"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Directory to cache downloaded TSE ZIP files"
    ),
) -> None:
    """
    Download and import electoral results from the TSE open data portal.

    Downloads a ZIP file (~50–200 MB) from cdn.tse.jus.br.
    Use --cache-dir to avoid re-downloading on subsequent runs.

    Example:
      history import-elections --year 2022 --position "DEPUTADO FEDERAL" --state SP
    """
    from src.sources.tse import TSEClient, ELECTION_YEARS

    if year not in ELECTION_YEARS:
        console.print(f"[red]Year {year} not available. Use one of: {ELECTION_YEARS}[/red]")
        raise typer.Exit(1)

    cache_path = Path(cache_dir) if cache_dir else None
    store = _store()

    with console.status(f"Downloading TSE data for {year}…  (this may take a minute)"):
        try:
            with TSEClient(cache_dir=cache_path) as tse:
                results = tse.fetch_candidates(
                    year=year,
                    state=state,
                    position=position,
                    limit=limit,
                )
        except Exception as exc:
            console.print(f"[red]TSE download failed: {exc}[/red]")
            raise typer.Exit(1)

    console.print(f"  Parsed {len(results):,} candidate records for {year}")

    if not dry_run:
        saved = store.upsert_election_results(results)
        console.print(f"[green]✓ Saved {saved:,} election records for {year}[/green]")
    else:
        elected = sum(1 for r in results if r.elected)
        console.print(
            f"[dim]Dry-run: would save {len(results):,} records ({elected} elected)[/dim]"
        )


# ---------------------------------------------------------------------------
# export-yaml
# ---------------------------------------------------------------------------


@app.command("export-yaml")
def export_yaml(
    record_id: str = typer.Argument(..., help="Record ID to export"),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o", help="Directory to write YAML (defaults to data/figures or data/events)"
    ),
) -> None:
    """
    Export a historical record as a YAML file to the knowledge base (data/).

    Politicians are saved to data/figures/.
    Events are saved to data/events/.
    """
    store = _store()

    # Try politician
    pol = store.get_politician(record_id)
    if pol:
        yaml_data = {
            "id": pol.id.replace("wikidata:", "").replace("camara:", "pol-"),
            "full_name": pol.name,
            "birth_date": pol.birth_date,
            "birth_place": pol.birth_place,
            "education": pol.education,
            "career": [
                {
                    "role": r.role,
                    "institution": r.institution,
                    "start_date": r.start_date,
                    "end_date": r.end_date,
                }
                for r in pol.roles
            ],
            "party_affiliations": [pol.party] if pol.party else [],
            "tags": pol.tags,
            "sources": pol.sources,
            "last_updated": dt.datetime.utcnow().isoformat(),
            "_source": "wikidata",
        }
        target_dir = Path(output_dir) if output_dir else _DATA_DIR / "figures"
        target_dir.mkdir(parents=True, exist_ok=True)
        slug = pol.name.lower().replace(" ", "-").replace(".", "")
        out_path = target_dir / f"{slug}.yaml"
        out_path.write_text(
            yaml.dump(yaml_data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        console.print(f"[green]✓ Wrote politician YAML: {out_path}[/green]")
        return

    # Try event
    event = store.get_event(record_id)
    if event:
        yaml_data = {
            "id": event.id.replace("event:wikidata:", "").replace("event:", ""),
            "title": event.title,
            "date": event.date,
            "end_date": event.end_date,
            "type": event.type,
            "summary": event.summary,
            "detailed_description": event.detailed_description,
            "significance": event.significance,
            "actors": event.actors,
            "institutions_involved": event.institutions,
            "tags": event.tags,
            "sources": event.sources,
            "last_updated": dt.datetime.utcnow().isoformat(),
            "_source": "wikidata",
        }
        target_dir = Path(output_dir) if output_dir else _DATA_DIR / "events"
        target_dir.mkdir(parents=True, exist_ok=True)
        slug = event.title.lower().replace(" ", "-")[:50]
        out_path = target_dir / f"{slug}.yaml"
        out_path.write_text(
            yaml.dump(yaml_data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        console.print(f"[green]✓ Wrote event YAML: {out_path}[/green]")
        return

    console.print(f"[red]Record not found: {record_id}[/red]")
    raise typer.Exit(1)
