"""
Seed DB with cabinet staff (secretários parlamentares + CNE assessores) from
the Câmara dos Deputados funcionarios bulk JSON file.

Source (single file, current snapshot of ALL Câmara staff):
  https://dadosabertos.camara.leg.br/arquivos/funcionarios/json/funcionarios.json

Relevant groups (filtered to those assigned to a deputy via uriLotacao)
────────────────────────────────────────────────────────────────────────
  codGrupo=6  Secretário Parlamentar          ~10,000 records
  codGrupo=2  Cargo de Natureza Especial       ~1,700 records (senior CNE assessores)

Note: this snapshot has NO CPF field — only name, role, appointment date, and
the deputy's Câmara ID extracted from uriLotacao.  The cross-reference value is
still high: ghost-employee detection, nepotism (surname match), revolving door
once the full expense data is loaded.

Refresh cadence: every ~6 months (or after a major cabinet reshuffle).
Each run creates a NEW snapshot tagged with the current YYYY-MM — old snapshots
are preserved so you can track staff turnover over time.
Use --force to re-fetch and overwrite the snapshot for the CURRENT month only.

Usage:
  python output/seed_secretarios.py               # fetch & load this month's snapshot
  python output/seed_secretarios.py --force       # re-download + overwrite this month
  python output/seed_secretarios.py --dry-run     # parse & show stats, no DB write
"""

import argparse
import datetime
import json
import logging
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Optional

sys.path.insert(0, ".")

from src.history.models import CabinetStaff
from src.history.store import HistoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FUNCIONARIOS_URL = (
    "https://dadosabertos.camara.leg.br/arquivos/funcionarios/json/funcionarios.json"
)
CACHE_FILE = Path("output/.secretarios_cache/funcionarios.json")

# Groups to import (only records where uriLotacao points to a deputy)
INCLUDE_GROUPS = {
    6: "Secretário Parlamentar",
    2: "Cargo de Natureza Especial",
}
CURRENT_LEGISLATURE = 57
# Tag each run with the current YYYY-MM so snapshots accumulate over time
SNAPSHOT_MONTH = datetime.date.today().strftime("%Y-%m")


# ── Fetch + cache ──────────────────────────────────────────────────────────────

def fetch_funcionarios(force: bool = False) -> list:
    """Download (or return cached) the full funcionarios JSON."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists() and not force:
        log.info(f"Using cached file: {CACHE_FILE}")
        data = json.loads(CACHE_FILE.read_text())
    else:
        log.info(f"Downloading {FUNCIONARIOS_URL} ...")
        try:
            req = urllib.request.Request(
                FUNCIONARIOS_URL, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except Exception as e:
            log.error(f"Download failed: {e}")
            sys.exit(1)
        data = json.loads(raw)
        CACHE_FILE.write_text(raw.decode())
        log.info(f"Downloaded and cached to {CACHE_FILE}")

    records = data.get("dados", data) if isinstance(data, dict) else data
    log.info(f"Total staff records in file: {len(records):,}")
    return records


# ── Parse ──────────────────────────────────────────────────────────────────────

def _extract_deputy_id(uri: str) -> Optional[int]:
    """Extract numeric deputy ID from uriLotacao like .../deputados/12345."""
    if not uri or "/deputados/" not in uri:
        return None
    try:
        return int(uri.rstrip("/").split("/")[-1])
    except ValueError:
        return None


def _extract_deputy_name(lotacao: str) -> str:
    """Extract deputy name from 'GAB. 4/906 - PASTOR EURICO'."""
    if " - " in lotacao:
        return lotacao.split(" - ", 1)[1].strip()
    return ""


def _normalise_date(raw: str) -> Optional[str]:
    """YYYY-MM-DD or DD/MM/YYYY → YYYY-MM-DD. Empty → None."""
    if not raw:
        return None
    raw = raw.strip()[:10]
    if len(raw) == 10 and raw[4] == "-":
        return raw
    if len(raw) == 10 and raw[2] == "/":
        d, m, y = raw.split("/")
        return f"{y}-{m}-{d}"
    return raw or None


def parse_records(records: list) -> list:
    """Filter to deputy-assigned staff and convert to CabinetStaff models."""
    staff = []
    skipped_no_dep = 0

    for rec in records:
        group = rec.get("codGrupo")
        if group not in INCLUDE_GROUPS:
            continue

        dep_id = _extract_deputy_id(rec.get("uriLotacao", ""))
        if dep_id is None:
            # CNE staff assigned to committees/organs, not a deputy — skip
            skipped_no_dep += 1
            continue

        start_date = _normalise_date(
            rec.get("dataNomeacao") or rec.get("dataInicioHistorico") or ""
        )
        # funcao has the human-readable role; cargo is the grade code (CNE10, etc.)
        role = rec.get("funcao") or rec.get("cargo") or INCLUDE_GROUPS.get(group, "")

        staff.append(CabinetStaff(
            deputy_camara_id=dep_id,
            deputy_name=_extract_deputy_name(rec.get("lotacao", "")),
            staff_name=rec.get("nome", "").strip(),
            staff_cpf=None,   # not provided in this dataset
            role=role,
            start_date=start_date,
            end_date=None,    # snapshot = all currently active
            legislature=CURRENT_LEGISLATURE,
            snapshot_month=SNAPSHOT_MONTH,
        ))

    log.info(
        f"Parsed {len(staff):,} deputy-assigned staff  "
        f"(skipped {skipped_no_dep:,} non-deputy CNE/organ assignments)"
    )
    return staff


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Seed cabinet staff from Câmara funcionarios JSON"
    )
    ap.add_argument(
        "--force", action="store_true",
        help="Re-download and overwrite the snapshot for the CURRENT month (older snapshots kept)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Parse and show stats without writing to DB",
    )
    args = ap.parse_args()

    store = HistoryStore()

    # Skip if we already have a snapshot for this month (unless --force)
    if not args.force and not args.dry_run:
        existing = store._db.execute(
            "SELECT COUNT(*) FROM cabinet_staff WHERE snapshot_month = ?",
            [SNAPSHOT_MONTH],
        ).fetchone()[0]
        if existing:
            log.info(
                f"Snapshot for {SNAPSHOT_MONTH} already exists ({existing:,} rows). "
                f"Use --force to re-fetch and overwrite it."
            )
            print("\nDB stats:")
            for k, v in store.stats().items():
                print(f"  {k:<25} {v:>10,}")
            return

    records = fetch_funcionarios(force=args.force)

    print("\nGroup breakdown in file:")
    for g, cnt in sorted(Counter(r.get("codGrupo") for r in records).items()):
        name = {
            1: "Quadro Efetivo RJU",
            2: "Cargo Natureza Especial",
            5: "Parlamentar",
            6: "Secretário Parlamentar",
        }.get(g, str(g))
        print(f"  codGrupo={g}  {name:<35}  {cnt:>6,}")

    staff = parse_records(records)

    print(f"\nSnapshot month: {SNAPSHOT_MONTH}")
    print(f"Sample (first 5):")
    for s in staff[:5]:
        print(f"  [{s.deputy_camara_id}] {s.deputy_name:<30} | {s.staff_name:<35} | {s.role[:55]}")

    if args.dry_run:
        print(f"\n[dry-run] Would save {len(staff):,} records tagged {SNAPSHOT_MONTH} — not writing to DB")
        return

    # If force: delete only this month's snapshot before re-inserting
    if args.force:
        deleted = store._db.execute(
            "DELETE FROM cabinet_staff WHERE snapshot_month = ?", [SNAPSHOT_MONTH]
        ).rowcount
        log.info(f"Cleared {deleted:,} existing rows for snapshot {SNAPSHOT_MONTH}")

    saved = store.upsert_staff(staff)
    print(f"\n✓ {saved:,} staff records saved (snapshot: {SNAPSHOT_MONTH})")

    # Show snapshot history so far
    snapshots = store._db.execute(
        "SELECT snapshot_month, COUNT(*) FROM cabinet_staff GROUP BY snapshot_month ORDER BY snapshot_month"
    ).fetchall()
    print("\nSnapshots in DB:")
    for month, count in snapshots:
        marker = " ← just added" if month == SNAPSHOT_MONTH else ""
        print(f"  {month}  {count:>6,} records{marker}")

    print("\nDB stats:")
    for k, v in store.stats().items():
        print(f"  {k:<25} {v:>10,}")
    print("\nDONE")


if __name__ == "__main__":
    main()
