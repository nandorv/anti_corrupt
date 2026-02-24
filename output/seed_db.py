"""
Interactive historical DB seeding script.
Run: python output/seed_db.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from src.sources.wikidata import WikidataClient
from src.history.store import HistoryStore

DB_PATH = Path("output/history.db")
store = HistoryStore(DB_PATH)

print("=" * 60)
print("ANTI-CORRUPT — Historical DB Seeding")
print("=" * 60)
print(f"DB: {DB_PATH}")
print(f"Pre-seed stats: {store.stats()}")
print()

# ── Reset: clear all tables for a clean re-seed ─────────────────────
print("Clearing existing data for fresh seed...")
for tbl in ("politicians", "historical_events", "legislatures",
            "politician_roles", "votes", "election_results", "expenses"):
    if tbl in store._db.table_names():
        store._db[tbl].delete_where()
print(f"Cleared. Stats now: {store.stats()}\n")

client = WikidataClient(timeout=90)

steps = [
    # --- Current mandate only (elected officials change every 4 years) ---
    ("Federal Deputies  (2023+, current)", lambda: client.fetch_federal_deputies(limit=600, since_year=2023), "politicians"),
    ("Senators          (2019+, current)", lambda: client.fetch_senators(limit=300, since_year=2019),        "politicians"),  # 2 cohorts: 2019 & 2023
    ("Governors         (2023+, current)", lambda: client.fetch_governors(limit=100, since_year=2023),       "politicians"),
    ("Mayors            (2024+, current)", lambda: client.fetch_mayors(limit=5500, since_year=2024),         "politicians"),  # ~5,570 municipalities
    # --- Key institutions: all history ---
    ("Presidents        (all time)",       lambda: client.fetch_presidents(),                                 "politicians"),
    ("STF Ministers     (all time)",       lambda: client.fetch_stf_ministers(),                              "politicians"),
    ("Gov Ministers     (all time)",       lambda: client.fetch_government_ministers(limit=1000),             "politicians"),
    ("TCU Ministers     (all time)",       lambda: client.fetch_tcu_ministers(),                              "politicians"),
    # --- Events: full history, 4 sub-queries ---
    ("Political Events  (all history)",   lambda: client.fetch_political_events(limit=2000),                 "events"),
    # --- Structure ---
    ("Legislatures",                      lambda: client.fetch_legislatures(),                               "legislatures"),
]

for label, fn, kind in steps:
    print(f"  ⏳ Fetching {label}...", end=" ", flush=True)
    try:
        records = fn()
        if kind == "politicians":
            saved = store.upsert_politicians(records)
        elif kind == "events":
            saved = store.upsert_events(records)
        else:
            saved = store.upsert_legislatures(records)
        print(f"✓ {saved} records saved")
    except Exception as exc:
        print(f"✗ FAILED: {exc}")

print()
print("=" * 60)
print("FINAL STATS:")
for k, v in store.stats().items():
    print(f"  {k:<25} {v:>6,}")
print("=" * 60)

# Show sample politicians per category
import json
db = store._db
print("\nSample by category:")
for tag, count_expected in [("deputado-federal", 450), ("senador", 80), ("governador", 27),
                              ("prefeito", 2000), ("presidente", 10), ("stf", 40),
                              ("ministro", 100), ("tcu", 10)]:
    rows = list(db.execute(
        "SELECT name, party, summary FROM politicians WHERE tags LIKE ? LIMIT 3",
        [f"%{tag}%"]
    ).fetchall())
    actual = db.execute(
        "SELECT COUNT(*) FROM politicians WHERE tags LIKE ?", [f"%{tag}%"]
    ).fetchone()[0]
    status = "✓" if actual >= count_expected // 2 else "⚠️"
    print(f"\n  {status} [{tag}] → {actual} total  (expected ≥{count_expected // 2})")
    for name, party, summary in rows:
        print(f"      {name:<35}  {party or '—':<15}  {(summary or '')[:60]}")

# Show sample events
print("\nSample events (most recent 5):")
for e in store.search_events("", limit=5):
    print(f"  [{e.type}] {e.date or '—'}  {e.title[:60]}")
    if e.summary:
        print(f"    → {e.summary[:80]}")
