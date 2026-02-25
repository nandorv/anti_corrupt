"""
Historical DB seeding script — uses official Brazilian government APIs.

Sources:
  Deputies   → Câmara API  (dadosabertos.camara.leg.br)
  Senators   → Senado API  (legis.senado.leg.br/dadosabertos)
  Governors  → TSE 2022    (cdn.tse.jus.br)
  Mayors     → TSE 2024    (cdn.tse.jus.br)
  Presidents / STF / Ministers / Events / Legislatures → Wikidata (fallback)

Run: python output/seed_db.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from src.sources.camara_api import CamaraAPI
from src.sources.senado_api import SenadoAPI
from src.sources.tse import TSEClient
from src.sources.wikidata import WikidataClient
from src.history.store import HistoryStore

DB_PATH = Path("output/history.db")
TSE_CACHE = Path("output/.tse_cache")          # disk cache for large ZIP files

store = HistoryStore(DB_PATH)

print("=" * 60)
print("ANTI-CORRUPT — Historical DB Seeding (official APIs)")
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

camara  = CamaraAPI()
senado  = SenadoAPI()
tse     = TSEClient(timeout=300, cache_dir=TSE_CACHE)
wiki    = WikidataClient(timeout=90)

steps = [
    # ── Current elected officials ── official authoritative APIs ────
    ("Federal Deputies  (2023–2027, Câmara API)",
        lambda: camara.fetch_current_deputies(legislature=57),           "politicians", None),
    ("Senators          (current, Senado API)",
        lambda: senado.fetch_current_senators(),                         "politicians", None),
    # TSE: primary source; Wikidata used as fallback if CDN is unreachable
    ("Governors         (2022 election, TSE)",
        lambda: tse.fetch_elected(year=2022, cargo="GOVERNADOR"),        "politicians",
        lambda: wiki.fetch_governors(limit=100, since_year=2023)),
    ("Mayors            (2024 election, TSE)",
        lambda: tse.fetch_elected(year=2024, cargo="PREFEITO"),          "politicians", None),
    # ── Key institutions — all history — Wikidata ──────────────────
    ("Presidents        (all time, Wikidata)",
        lambda: wiki.fetch_presidents(),                                 "politicians", None),
    ("STF Ministers     (all time, Wikidata)",
        lambda: wiki.fetch_stf_ministers(),                              "politicians", None),
    ("Gov Ministers     (all time, Wikidata)",
        lambda: wiki.fetch_government_ministers(limit=1000),             "politicians", None),
    ("TCU Ministers     (all time, Wikidata)",
        lambda: wiki.fetch_tcu_ministers(),                              "politicians", None),
    # ── Events & structure ─────────────────────────────────────────
    ("Political Events  (all history, Wikidata)",
        lambda: wiki.fetch_political_events(limit=2000),                 "events",      None),
    ("Legislatures      (Wikidata)",
        lambda: wiki.fetch_legislatures(),                               "legislatures", None),
]

for label, fn, kind, fallback_fn in steps:
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
        if fallback_fn is not None:
            print(f"    ↳ Wikidata fallback...", end=" ", flush=True)
            try:
                records = fallback_fn()
                if kind == "politicians":
                    saved = store.upsert_politicians(records)
                elif kind == "events":
                    saved = store.upsert_events(records)
                else:
                    saved = store.upsert_legislatures(records)
                print(f"✓ {saved} records saved (fallback)")
            except Exception as exc2:
                print(f"✗ Fallback also failed: {exc2}")

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
for tag, count_expected in [
    ("deputado-federal", 500),   # Câmara API: exactly 513
    ("senador",          75),    # Senado API: ~81 in exercise
    ("governador",       25),    # TSE 2022:   27 states
    ("prefeito",         5000),  # TSE 2024:   ~5,570 municipalities
    ("presidente",       5),
    ("stf",              15),
    ("ministro",         100),
    ("tcu",              5),
]:
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
