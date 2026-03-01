"""
History CLI — build and query the historical political database.

Primary data (seeded from TSE CSV files):
  output/seed_eleicoes.py   — elected officials from TSE consulta_cand CSVs
  output/seed_magistrados.py — judges + ministers from magistrados_brasil.csv

Commands:
  stats              — row counts per table
  list               — list politicians with optional filters
  search             — full-text / CPF / tag search
  show               — display one record by ID
  import-csv         — import any CSV with nome,sede,tribunal,cargo
  import-elections   — (re-)import a TSE consulta_cand local CSV file
  import-votes       — import voting history from the Câmara API
  import-expenses    — import CEAP expenses from the Câmara API
  fetch-wiki         — supplement data from Wikidata (no key required)
  enrich             — look up a person or topic on Wikipedia
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
# list
# ---------------------------------------------------------------------------


@app.command("list")
def list_politicians(
    tag: Optional[str] = typer.Option(
        None, "--tag", "-t",
        help="Filter by tag (e.g. stf, magistrado, executivo_federal, DEPUTADO FEDERAL)",
    ),
    state: Optional[str] = typer.Option(None, "--state", "-s", help="State UF (e.g. SP, RJ)"),
    party: Optional[str] = typer.Option(None, "--party", "-p", help="Party (e.g. PT, PL)"),
    source: Optional[str] = typer.Option(
        None, "--source",
        help="ID prefix filter: tse | csv | wikidata | camara",
    ),
    position: Optional[str] = typer.Option(
        None, "--position",
        help="Election position substring (e.g. DEPUTADO FEDERAL, SENADOR)",
    ),
    limit: int = typer.Option(30, "--limit", "-n", help="Max results to show"),
) -> None:
    """
    List politicians from the database with optional filters.

    Examples:
      history list --tag stf
      history list --tag magistrado --limit 50
      history list --position "DEPUTADO FEDERAL" --state SP
      history list --source tse --party PT --limit 20
    """
    store = _store()
    politicians = store.list_politicians_filtered(
        tag=tag, state=state, party=party,
        source_prefix=source, position=position, limit=limit,
    )

    if not politicians:
        console.print("[yellow]No politicians found with those filters.[/yellow]")
        raise typer.Exit(0)

    active_filters = []
    if tag:      active_filters.append(f"tag={tag}")
    if state:    active_filters.append(f"state={state}")
    if party:    active_filters.append(f"party={party}")
    if source:   active_filters.append(f"source={source}")
    if position: active_filters.append(f"position={position}")
    title = "Politicians" + (f" — {', '.join(active_filters)}" if active_filters else "")

    t = Table(title=title, box=box.SIMPLE, show_header=True)
    t.add_column("ID", style="dim", no_wrap=True)
    t.add_column("Name", style="bold")
    t.add_column("State", width=5)
    t.add_column("Party", width=8)
    t.add_column("Role / Position")
    t.add_column("Tags", style="dim")

    for p in politicians:
        role_str = p.roles[0].role if p.roles else "—"
        tags_str = ", ".join(p.tags[:3]) + ("…" if len(p.tags) > 3 else "")
        t.add_row(p.id, p.name, p.state or "—", p.party or "—", role_str, tags_str)

    console.print(t)
    console.print(f"[dim]Showing {len(politicians)} of {store.count_politicians():,} politicians[/dim]")


# ---------------------------------------------------------------------------
# import-csv
# ---------------------------------------------------------------------------


@app.command("import-csv")
def import_csv_file(
    path: str = typer.Argument(..., help="CSV file path (nome,sede,tribunal,cargo)"),
    source_tag: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source tag override (default: csv:<filename>)"
    ),
    mandate_start: Optional[str] = typer.Option(
        None, "--start", help="Role start date YYYY-MM-DD"
    ),
    mandate_end: Optional[str] = typer.Option(
        None, "--end", help="Role end date YYYY-MM-DD"
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    Import politicians from a flat CSV file (nome, sede, tribunal, cargo).

    This is the standard format for all non-electoral imports: judges,
    ministers, council members, etc.

    Examples:
      history import-csv eleicoes/magistrados_brasil.csv
      history import-csv data/novos_ministros.csv --start 2025-01-01
    """
    from src.sources.csv_import import CSVImporter
    from pathlib import Path as _Path

    csv_path = _Path(path)
    if not csv_path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    with console.status(f"Parsing {csv_path.name}…"):
        try:
            politicians = CSVImporter.load(
                csv_path,
                source_tag=source_tag,
                mandate_start=mandate_start,
                mandate_end=mandate_end,
            )
        except ValueError as exc:
            console.print(f"[red]CSV format error: {exc}[/red]")
            raise typer.Exit(1)

    console.print(f"  Parsed [bold]{len(politicians):,}[/bold] politicians from {csv_path.name}")

    if dry_run:
        # Show a preview table
        t = Table(title=f"Preview — {csv_path.name}", box=box.SIMPLE)
        t.add_column("ID", style="dim")
        t.add_column("Name", style="bold")
        t.add_column("State")
        t.add_column("Role")
        t.add_column("Institution")
        for p in politicians[:10]:
            r = p.roles[0] if p.roles else None
            t.add_row(p.id, p.name, p.state or "—", r.role if r else "—", r.institution if r else "—")
        if len(politicians) > 10:
            t.add_row("…", f"(+{len(politicians)-10} more)", "", "", "")
        console.print(t)
        console.print("[dim]Dry-run: nothing written.[/dim]")
        return

    store = _store()
    saved = store.upsert_politicians(politicians)
    console.print(f"[green]✓ Upserted {saved:,} politicians from {csv_path.name}[/green]")
    totals = store.stats()
    console.print(f"[dim]Total politicians in DB: {totals['politicians']:,}[/dim]")


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
            t.add_column("ID", style="dim", no_wrap=True)
            t.add_column("Name", style="bold")
            t.add_column("Party")
            t.add_column("State")
            t.add_column("CPF", style="dim")
            t.add_column("Roles")
            for p in politicians:
                role_str = _fmt_list([r.role for r in p.roles], max_items=2)
                t.add_row(p.id, p.name, p.party or "—", p.state or "—", p.cpf or "—", role_str)
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

    # All known politician ID prefixes
    POL_PREFIXES = ("wikidata:", "camara:", "pol:", "tse:", "csv:")

    # Try politicians first
    if any(record_id.startswith(p) for p in POL_PREFIXES):
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
    file: str = typer.Argument(
        ...,
        help="Path to a local TSE consulta_cand CSV file (e.g. eleicoes/consulta_cand_2022_BRASIL.csv)",
    ),
    year: int = typer.Option(
        ..., "--year", "-y",
        help="Election year encoded in this file (e.g. 2022 or 2024)",
    ),
    skip_cargo: Optional[str] = typer.Option(
        None, "--skip",
        help="Comma-separated cargo names to exclude (e.g. 'VEREADOR,VICE-PREFEITO')",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    Import elected candidates from a local TSE consulta_cand CSV file.

    The file must be a TSE 'consulta_cand' semicolon-delimited CSV in
    Latin-1 encoding (standard TSE open-data format).

    Only ELECTED candidates are imported (DS_SIT_TOT_TURNO in
    ELEITO / ELEITO POR QP / ELEITO POR MÉDIA).

    Examples:
      history import-elections eleicoes/consulta_cand_2022_BRASIL.csv --year 2022
      history import-elections eleicoes/consulta_cand_2024_BRASIL.csv --year 2024 --skip VEREADOR
    """
    import csv as _csv
    from pathlib import Path as _Path
    from src.history.models import PoliticianRole, ElectionResult

    csv_path = _Path(file)
    if not csv_path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    ELECTED = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}
    CARGO_META = {
        "DEPUTADO FEDERAL":   ("Deputado Federal",        "camara_dos_deputados",     "2023-02-01", "2027-01-31"),
        "DEPUTADO ESTADUAL":  ("Deputado Estadual",       "assembleia_legislativa",   "2023-01-01", "2026-12-31"),
        "DEPUTADO DISTRITAL": ("Deputado Distrital",      "camara_legislativa_df",    "2023-01-01", "2026-12-31"),
        "SENADOR":            ("Senador",                 "senado_federal",           "2023-02-01", "2031-01-31"),
        "GOVERNADOR":         ("Governador",              "governo_estadual",         "2023-01-01", "2026-12-31"),
        "VICE-GOVERNADOR":    ("Vice-Governador",         "governo_estadual",         "2023-01-01", "2026-12-31"),
        "1º SUPLENTE":        ("1º Suplente Senado",      "senado_federal",           "2023-02-01", None),
        "2º SUPLENTE":        ("2º Suplente Senado",      "senado_federal",           "2023-02-01", None),
        "PRESIDENTE":         ("Presidente da República", "presidencia_da_republica", "2023-01-01", "2026-12-31"),
        "VICE-PRESIDENTE":    ("Vice-Presidente",         "presidencia_da_republica", "2023-01-01", "2026-12-31"),
        "PREFEITO":           ("Prefeito",                "prefeitura_municipal",     "2025-01-01", "2028-12-31"),
        "VEREADOR":           ("Vereador",                "camara_municipal",         "2025-01-01", "2028-12-31"),
    }
    MANDATE_BY_YEAR = {2022: ("2023-01-01", "2026-12-31"), 2024: ("2025-01-01", "2028-12-31")}
    skip_set = {s.strip().upper() for s in (skip_cargo or "").split(",") if s.strip()}

    def _get(row, idx, col):
        i = idx.get(col)
        return row[i].strip('"') if i is not None and i < len(row) else ""

    def _null(val):
        return None if val in ("#NULO", "", "#NE") else val

    politicians_out: list = []
    results_out: list[ElectionResult] = []
    seen: set[str] = set()
    skipped = 0
    default_start, default_end = MANDATE_BY_YEAR.get(year, ("2023-01-01", None))
    source_tag = f"tse:consulta_cand_{year}"

    _csv.field_size_limit(10_000_000)
    with console.status(f"Parsing {csv_path.name}…"):
        with open(csv_path, encoding="latin1", errors="replace") as f:
            reader = _csv.reader(f, delimiter=";")
            headers = [h.strip('"') for h in next(reader)]
            idx = {h: i for i, h in enumerate(headers)}

            for row in reader:
                try:
                    if _get(row, idx, "DS_SIT_TOT_TURNO") not in ELECTED:
                        continue
                    cargo = _get(row, idx, "DS_CARGO")
                    if cargo in skip_set:
                        continue
                    seq = _get(row, idx, "SQ_CANDIDATO")
                    if seq in seen:
                        continue
                    seen.add(seq)

                    name       = _get(row, idx, "NM_CANDIDATO")
                    party      = _get(row, idx, "SG_PARTIDO")
                    uf         = _get(row, idx, "SG_UF")
                    cpf        = _null(_get(row, idx, "NR_CPF_CANDIDATO"))
                    birth_date = _null(_get(row, idx, "DT_NASCIMENTO"))
                    municipio  = _null(_get(row, idx, "NM_UE"))
                    turno      = _get(row, idx, "NR_TURNO") or "1"
                    colig      = _null(_get(row, idx, "NM_COLIGACAO"))
                    nr         = _get(row, idx, "NR_CANDIDATO")

                    if birth_date and len(birth_date) == 10 and birth_date[2] == "/":
                        d, m, y = birth_date.split("/")
                        birth_date = f"{y}-{m}-{d}"

                    meta = CARGO_META.get(cargo)
                    from src.history.models import Politician as _Politician
                    role = PoliticianRole(
                        role=meta[0] if meta else cargo,
                        institution=meta[1] if meta else "desconhecida",
                        start_date=meta[2] if meta else default_start,
                        end_date=meta[3] if meta else default_end,
                        notes=municipio if year == 2024 else None,
                    )
                    politicians_out.append(_Politician(
                        id=f"tse:{seq}", name=name, party=party, state=uf,
                        birth_date=birth_date, tse_id=seq, cpf=cpf,
                        roles=[role], tags=[cargo, str(year), "eleito"],
                        sources=[source_tag],
                    ))
                    results_out.append(ElectionResult(
                        year=year, state=uf,
                        municipality=municipio if year == 2024 else None,
                        position=cargo, candidate_name=name, candidate_number=nr,
                        candidate_cpf=cpf, party=party, coalition=colig,
                        elected=True, round=int(turno) if turno.isdigit() else 1,
                        tse_seq_candidate=seq,
                    ))
                except Exception:
                    skipped += 1

    console.print(
        f"  Parsed [bold]{len(politicians_out):,}[/bold] elected candidates"
        + (f"  ({skipped} rows skipped)" if skipped else "")
    )

    if dry_run:
        console.print(f"[dim]Dry-run: would upsert {len(politicians_out):,} politicians and {len(results_out):,} election results.[/dim]")
        return

    store = _store()
    p_saved = store.upsert_politicians(politicians_out)
    r_saved = store.upsert_election_results(results_out)
    with_cpf = sum(1 for p in politicians_out if p.cpf)
    console.print(
        f"[green]✓ {p_saved:,} politicians ({with_cpf:,} with CPF) | "
        f"{r_saved:,} election results saved[/green]"
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
            "_source": pol.id.split(":")[0],  # tse / csv / wikidata / camara
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
