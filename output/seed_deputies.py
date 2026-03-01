#!/usr/bin/env python3
"""
seed_deputies.py — Bulk-import votes and CEAP expenses for all 513
                    Deputados Federais (57th legislature, 2023-2027).

Voting strategy (session-centric):
  The Câmara API does NOT expose a per-deputy vote endpoint.  The correct
  approach is:
    1. GET /votacoes?dataInicio=...&dataFim=...  → list all sessions in range
    2. GET /votacoes/{id}/votos                 → all 400+ deputies for that session

  We iterate over every session in the requested date range and upsert the full
  vote slate.  This is efficient: ~110 sessions/month × 1 API call each.

Expense strategy (per-deputy):
  GET /deputados/{id}/despesas?ano={year}  — fully paginated, per-deputy.

Usage:
    python output/seed_deputies.py                          # all sessions 2023-2026
    python output/seed_deputies.py --start-year 2024 --end-year 2024
    python output/seed_deputies.py --start-month 2024-02 --end-month 2024-02
    python output/seed_deputies.py --votes-only             # skip expenses
    python output/seed_deputies.py --expenses-only          # skip votes
    python output/seed_deputies.py --resume                 # skip already-done data
    python output/seed_deputies.py --limit 5               # first 5 deputies (expenses only)
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.history.models import Expense, Politician, PoliticianRole, Vote
from src.history.store import HistoryStore
from src.sources.camara_api import CamaraAPI, CamaraAPIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_PATH        = ROOT / "output" / "history.db"
LEGISLATURE    = 57          # 2023-2027
START_YEAR     = 2023
END_YEAR       = 2026

# ── Rate-limit knobs ──────────────────────────────────────────────────────────
DELAY_BETWEEN_SESSIONS  = 0.5    # seconds between /votacoes/{id}/votos calls
DELAY_BETWEEN_DEPUTIES  = 1.2    # seconds between /deputados/{id}/despesas calls
DELAY_AFTER_ERROR       = 5.0    # seconds after any error
MAX_RETRIES             = 3      # per session/deputy before giving up


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_session_votes(raw: list[dict], session: dict) -> list[Vote]:
    """Convert raw /votacoes/{id}/votos response to Vote objects."""
    votes: list[Vote] = []
    session_id  = session.get("id", "")
    prop_obj    = session.get("proposicaoObjeto") or ""
    prop_uri    = session.get("uriProposicaoObjeto") or ""
    description = (session.get("descricao") or "")[:200]
    session_date = (session.get("data") or "")[:10]

    # Extract proposition ID from URI if available
    prop_id = ""
    if prop_uri:
        parts = prop_uri.rstrip("/").split("/")
        prop_id = parts[-1] if parts else ""

    for rv in raw:
        try:
            vote_type = (rv.get("tipoVoto") or "").strip().upper()
            dep_sub   = rv.get("deputado_") or {}
            dep_id    = dep_sub.get("id")
            dep_name  = dep_sub.get("nome") or ""
            party     = dep_sub.get("siglaPartido")
            state     = dep_sub.get("siglaUf")
            date_raw  = rv.get("dataRegistroVoto") or session_date
            date      = date_raw[:10] if date_raw else session_date

            if not vote_type or not dep_id:
                continue

            votes.append(Vote(
                deputy_camara_id=int(dep_id),
                deputy_id=f"camara:{dep_id}",
                deputy_name=dep_name,
                proposition_id=f"camara:prop:{prop_id}" if prop_id else f"camara:session:{session_id}",
                proposition_title=prop_obj or description,
                proposition_type=None,
                vote=vote_type,
                date=date,
                session_id=str(session_id),
                party=party,
                state=state,
            ))
        except Exception as exc:
            log.debug("Vote row skipped (session=%s): %s", session_id, exc)
    return votes


def _parse_expenses(raw: list[dict], deputy_id: int, deputy_name: str) -> list[Expense]:
    """Convert raw /deputados/{id}/despesas response to Expense objects."""
    expenses: list[Expense] = []
    for re_ in raw:
        try:
            value = float(re_.get("valorLiquido") or re_.get("valorDocumento") or 0)
            if value <= 0:
                continue
            exp_year  = int(re_.get("ano") or 0)
            exp_month = int(re_.get("mes") or 0)
            if exp_year == 0:
                continue
            expenses.append(Expense(
                deputy_camara_id=deputy_id,
                deputy_id=f"camara:{deputy_id}",
                deputy_name=deputy_name,
                year=exp_year,
                month=exp_month,
                category=(re_.get("tipoDespesa") or "OUTROS").strip(),
                supplier=(re_.get("nomeFornecedor") or "").strip(),
                supplier_cnpj_cpf=(re_.get("cnpjCpfFornecedor") or None),
                value=value,
                document_number=(re_.get("numDocumento") or None),
                description=(re_.get("descricao") or None),
            ))
        except Exception as exc:
            log.debug("Expense row skipped for deputy %d: %s", deputy_id, exc)
    return expenses


# ─────────────────────────────────────────────────────────────────────────────
# Deputy list helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_deputies(store: HistoryStore, api: CamaraAPI) -> list[tuple[int, str]]:
    """Return list of (camara_id, name) for all Deputados Federais."""
    db = store._db

    rows = db.execute(
        "SELECT camara_id, name FROM politicians "
        "WHERE camara_id IS NOT NULL AND id LIKE 'camara:%' "
        "ORDER BY name"
    ).fetchall()
    if rows:
        log.info("Using %d deputies from DB (camara: prefix)", len(rows))
        return [(int(r[0]), r[1]) for r in rows]

    log.info("No camara: records in DB — fetching deputy list from Câmara API...")
    raw = api.list_deputies(legislature=LEGISLATURE)
    log.info("Fetched %d deputies from Câmara API", len(raw))

    # Build a quick lookup for party/state
    raw_by_id = {int(d["id"]): d for d in raw if d.get("id")}

    deputies: list[tuple[int, str]] = [
        (int(d["id"]), d.get("nome") or "")
        for d in raw if d.get("id")
    ]

    # Upsert into politicians table
    pol_records = []
    for dep_id, name in deputies:
        d = raw_by_id.get(dep_id, {})
        pol_records.append(Politician(
            id=f"camara:{dep_id}",
            name=name,
            party=d.get("siglaPartido"),
            state=d.get("siglaUf"),
            camara_id=dep_id,
            roles=[PoliticianRole(
                role="Deputado Federal",
                institution="camara_dos_deputados",
                start_date="2023-02-01",
                end_date="2027-01-31",
            )],
            tags=["DEPUTADO FEDERAL", str(LEGISLATURE), "legislativo"],
            sources=[f"camara:legislature:{LEGISLATURE}"],
        ))
    store.upsert_politicians(pol_records)
    log.info("Upserted %d deputies into politicians table", len(pol_records))
    return deputies


def _month_ranges(start_year: int, end_year: int,
                  start_month: str | None = None,
                  end_month: str | None = None) -> list[tuple[str, str]]:
    """
    Build a list of (start_date, end_date) tuples, one per calendar month.

    If start_month/end_month (YYYY-MM) are given, they override start/end year.
    """
    if start_month:
        sy, sm = int(start_month[:4]), int(start_month[5:7])
    else:
        sy, sm = start_year, 1

    if end_month:
        ey, em = int(end_month[:4]), int(end_month[5:7])
    else:
        ey, em = end_year, 12

    ranges = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        last_day = calendar.monthrange(y, m)[1]
        ranges.append((f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last_day:02d}"))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return ranges


def _session_already_done(store: HistoryStore, session_id: str) -> bool:
    """Return True if we already have votes for this session."""
    return store._db.execute(
        "SELECT 1 FROM votes WHERE session_id = ? LIMIT 1", [session_id]
    ).fetchone() is not None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bulk-import Câmara votes and expenses")
    parser.add_argument("--start-year",    type=int,   default=START_YEAR)
    parser.add_argument("--end-year",      type=int,   default=END_YEAR)
    parser.add_argument("--start-month",   type=str,   default=None,
                        help="YYYY-MM override for votes start (e.g. 2024-02)")
    parser.add_argument("--end-month",     type=str,   default=None,
                        help="YYYY-MM override for votes end (e.g. 2024-02)")
    parser.add_argument("--resume",        action="store_true",
                        help="Skip sessions/deputies already in DB")
    parser.add_argument("--votes-only",    action="store_true")
    parser.add_argument("--expenses-only", action="store_true")
    parser.add_argument("--limit",         type=int,   default=0,
                        help="Max deputies for expenses (0 = all)")
    parser.add_argument("--session-delay", type=float, default=DELAY_BETWEEN_SESSIONS,
                        help=f"Seconds between session fetches (default: {DELAY_BETWEEN_SESSIONS})")
    parser.add_argument("--deputy-delay",  type=float, default=DELAY_BETWEEN_DEPUTIES,
                        help=f"Seconds between deputy expense fetches (default: {DELAY_BETWEEN_DEPUTIES})")
    args = parser.parse_args()

    do_votes    = not args.expenses_only
    do_expenses = not args.votes_only

    store = HistoryStore(DB_PATH)
    api   = CamaraAPI()

    months = _month_ranges(
        args.start_year, args.end_year,
        args.start_month, args.end_month,
    )

    print(f"\n{'─'*60}")
    print(f"  Mode        : {'votes + expenses' if do_votes and do_expenses else 'votes only' if do_votes else 'expenses only'}")
    if do_votes:
        print(f"  Vote period : {months[0][0]} → {months[-1][1]}  ({len(months)} months)")
    if do_expenses:
        print(f"  Exp. period : {args.start_year}–{args.end_year}")
    print(f"  Resume      : {'yes' if args.resume else 'no'}")
    print(f"{'─'*60}\n")

    # ── VOTES (session-centric) ───────────────────────────────────────────────
    total_votes = 0
    if do_votes:
        log.info("=== VOTE IMPORT (session-centric) ===")
        for month_start, month_end in months:
            log.info("Fetching sessions for %s → %s", month_start, month_end)

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    sessions = api.list_vote_sessions(
                        start_date=month_start,
                        end_date=month_end,
                    )
                    break
                except CamaraAPIError as exc:
                    if attempt < MAX_RETRIES:
                        log.warning("list_vote_sessions error (attempt %d/%d): %s — retrying in %.0fs",
                                    attempt, MAX_RETRIES, exc, DELAY_AFTER_ERROR)
                        time.sleep(DELAY_AFTER_ERROR)
                    else:
                        log.error("FAILED to list sessions for %s: %s", month_start, exc)
                        sessions = []

            log.info("  %d sessions found for %s", len(sessions), month_start[:7])

            for si, session in enumerate(sessions, 1):
                session_id  = str(session.get("id", ""))
                description = (session.get("descricao") or "")[:60]

                if args.resume and _session_already_done(store, session_id):
                    log.debug("  [%d/%d] skip %s (already done)", si, len(sessions), session_id)
                    continue

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        raw_votes = api.get_session_votes(session_id)
                        votes = _parse_session_votes(raw_votes, session)
                        if votes:
                            store.upsert_votes(votes)
                            total_votes += len(votes)
                        log.info("  [%d/%d] session %-20s  %3d votes  %s",
                                 si, len(sessions), session_id, len(votes), description[:50])
                        break
                    except CamaraAPIError as exc:
                        if attempt < MAX_RETRIES:
                            log.warning("  session %s error (attempt %d/%d) — retry in %.0fs",
                                        session_id, attempt, MAX_RETRIES, DELAY_AFTER_ERROR)
                            time.sleep(DELAY_AFTER_ERROR)
                        else:
                            log.error("  FAILED session %s: %s", session_id, exc)

                if si < len(sessions):
                    time.sleep(args.session_delay)

        log.info("=== Votes done: %d records inserted ===", total_votes)

    # ── EXPENSES (per-deputy) ─────────────────────────────────────────────────
    total_expenses = 0
    if do_expenses:
        log.info("=== EXPENSE IMPORT (per-deputy) ===")
        deputies = _get_deputies(store, api)
        if args.limit:
            deputies = deputies[:args.limit]

        n_deps   = len(deputies)
        errors   = 0
        skipped  = 0

        for i, (dep_id, dep_name) in enumerate(deputies, 1):
            prefix = f"[{i:>3}/{n_deps}]  {dep_name:<40}  (id={dep_id})"

            if args.resume:
                if store._db.execute(
                    "SELECT 1 FROM expenses WHERE deputy_camara_id = ? LIMIT 1", [dep_id]
                ).fetchone():
                    log.debug("  skip %s (expenses in DB)", dep_name)
                    skipped += 1
                    continue

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    all_raw: list[dict] = []
                    for yr in range(args.start_year, args.end_year + 1):
                        raw_exp = api.get_deputy_expenses(dep_id, year=yr)
                        all_raw.extend(raw_exp)
                        if yr < args.end_year:
                            time.sleep(0.3)

                    expenses = _parse_expenses(all_raw, dep_id, dep_name)
                    if expenses:
                        store.upsert_expenses(expenses)
                        total_expenses += len(expenses)
                    total_value = sum(e.value for e in expenses)
                    print(f"{prefix}  ✓  {len(expenses)} recs  R${total_value:,.0f}")
                    break

                except CamaraAPIError as exc:
                    if attempt < MAX_RETRIES:
                        log.warning("  %s error (attempt %d/%d) — retry in %.0fs",
                                    dep_name, attempt, MAX_RETRIES, DELAY_AFTER_ERROR)
                        time.sleep(DELAY_AFTER_ERROR)
                    else:
                        log.error("  ✗ FAILED %s: %s", dep_name, exc)
                        errors += 1
                        print(f"{prefix}  ✗ FAILED")

                except Exception as exc:
                    log.error("  ✗ Unexpected error for %s: %s", dep_name, exc, exc_info=True)
                    errors += 1
                    print(f"{prefix}  ✗ ERROR — {exc}")
                    break

            if i < n_deps:
                time.sleep(args.deputy_delay)

        log.info("=== Expenses done: %d records (%d errors, %d skipped) ===",
                 total_expenses, errors, skipped)

    # ── Summary ───────────────────────────────────────────────────────────────
    stats = store.stats()
    print(f"\n{'='*60}")
    print(f"  Votes inserted  : {total_votes:,}  (DB total: {stats.get('votes', 0):,})")
    print(f"  Expenses added  : {total_expenses:,}  (DB total: {stats.get('expenses', 0):,})")
    print(f"{'='*60}")
    print("DONE")


if __name__ == "__main__":
    main()
