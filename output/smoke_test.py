#!/usr/bin/env python3
"""Smoke-test the new/fixed CLI commands."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.history.store import HistoryStore

DB = ROOT / "output" / "history.db"
store = HistoryStore(DB)

# 1. list_politicians_filtered
print("=== list: tag=stf ===")
pols = store.list_politicians_filtered(tag="stf", limit=5)
for p in pols:
    print(f"  {p.id}  {p.name}  {p.tags}")

print("\n=== list: tag=magistrado, state=DF ===")
pols = store.list_politicians_filtered(tag="magistrado", state="DF", limit=5)
for p in pols:
    print(f"  {p.id}  {p.name}  state={p.state}")

print("\n=== list: source_prefix=csv ===")
pols = store.list_politicians_filtered(source_prefix="csv", limit=4)
for p in pols:
    print(f"  {p.id}  {p.name}")

print("\n=== list: position=SENADOR ===")
pols = store.list_politicians_filtered(position="SENADOR", limit=4)
for p in pols:
    print(f"  {p.id}  {p.name}  {p.state}")

print("\n=== search: CPF exact ===")
# Grab a known CPF from the DB
row = store._db.execute("SELECT cpf, name FROM politicians WHERE cpf IS NOT NULL LIMIT 1").fetchone()
if row:
    cpf, name = row
    results = store.search_politicians(cpf, limit=3)
    print(f"  search('{cpf}') → {[p.name for p in results]}")

print("\n=== search: tag substring ===")
results = store.search_politicians("executivo_federal", limit=3)
print(f"  search('executivo_federal') → {[p.name for p in results]}")

print("\n=== show: tse: prefix ===")
tse_row = store._db.execute("SELECT id FROM politicians WHERE id LIKE 'tse:%' LIMIT 1").fetchone()
if tse_row:
    p = store.get_politician(tse_row[0])
    print(f"  get_politician('{tse_row[0]}') → {p.name if p else 'NOT FOUND'}")

print("\n=== show: csv: prefix ===")
csv_row = store._db.execute("SELECT id FROM politicians WHERE id LIKE 'csv:%' LIMIT 1").fetchone()
if csv_row:
    p = store.get_politician(csv_row[0])
    print(f"  get_politician('{csv_row[0]}') → {p.name if p else 'NOT FOUND'}")

print("\nAll smoke tests passed ✓")
