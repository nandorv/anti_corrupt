#!/usr/bin/env python3
"""
seed_magistrados.py — import magistrados_brasil.csv (and any future
flat CSV files) into history.db using the standardised CSVImporter.

Usage:
    python output/seed_magistrados.py
    python output/seed_magistrados.py eleicoes/some_other_file.csv
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.history.store import HistoryStore
from src.sources.csv_import import CSVImporter

DB_PATH = ROOT / "output" / "history.db"

# Files to import  →  (optional source_tag override, mandate_start, mandate_end)
DEFAULT_FILES: list[tuple[Path, str | None, str | None, str | None]] = [
    (ROOT / "eleicoes" / "magistrados_brasil.csv", "magistrados_brasil", None, None),
]


def main(files=None):
    store = HistoryStore(DB_PATH)
    targets = files or DEFAULT_FILES

    total = 0
    for path, source_tag, start, end in targets:
        path = Path(path)
        if not path.exists():
            print(f"⚠  File not found: {path}")
            continue

        print(f"\n📂 Importing {path.name} …")
        politicians = CSVImporter.load(path, source_tag=source_tag, mandate_start=start, mandate_end=end)
        store.upsert_politicians(politicians)
        print(f"   ✅  {len(politicians)} politicians upserted")
        total += len(politicians)

    stats = store.stats()
    print(f"\n📊 DB totals after import:")
    for k, v in stats.items():
        print(f"   {k}: {v:,}")
    print(f"\n🎉 Done — added/updated {total} records total")


if __name__ == "__main__":
    # Allow passing extra CSV paths on the command line:
    #   python output/seed_magistrados.py eleicoes/foo.csv eleicoes/bar.csv
    if len(sys.argv) > 1:
        extra = [(Path(a), None, None, None) for a in sys.argv[1:]]
        main(extra)
    else:
        main()
