"""Quick DB summary query."""
import sys, json, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.history.store import HistoryStore

store = HistoryStore(Path(__file__).resolve().parent / "history.db")
db = store._db

print("=== TOTAL STATS ===")
for k, v in store.stats().items():
    print(f"  {k:<25} {v:>10,}")

print("\n=== POLITICIANS BY SOURCE ===")
for row in db.execute("""
    SELECT
      CASE
        WHEN id LIKE 'tse:%' THEN 'TSE (elected)'
        WHEN id LIKE 'csv:%' THEN 'CSV import'
        ELSE 'other'
      END AS source,
      COUNT(*) AS total
    FROM politicians
    GROUP BY 1 ORDER BY 2 DESC
""").fetchall():
    print(f"  {row[0]:<25} {row[1]:>8,}")

print("\n=== TSE: POSITIONS BREAKDOWN ===")
for row in db.execute("""
    SELECT position, COUNT(*) AS n
    FROM election_results
    GROUP BY position
    ORDER BY n DESC
""").fetchall():
    print(f"  {row[0]:<30} {row[1]:>6,}")

print("\n=== CSV: COUNT BY TRIBUNAL ===")
counts = collections.Counter()
for (tags_json,) in db.execute("SELECT tags FROM politicians WHERE id LIKE 'csv:%'").fetchall():
    tags = json.loads(tags_json) if tags_json else []
    counts[tags[0] if tags else "?"] += 1
for tag, n in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {tag:<25} {n:>5,}")

print("\n=== ALL STF JUSTICES ===")
for row in db.execute("""
    SELECT name, roles FROM politicians WHERE tags LIKE '%stf%' ORDER BY name
""").fetchall():
    roles = json.loads(row[1]) if row[1] else []
    cargo = roles[0]["role"] if roles else "?"
    print(f"  {row[0]:<35}  {cargo}")

print("\n=== MINISTERS (top 15 alphabetically) ===")
for row in db.execute("""
    SELECT name, roles FROM politicians WHERE tags LIKE '%executivo_federal%' ORDER BY name LIMIT 15
""").fetchall():
    roles = json.loads(row[1]) if row[1] else []
    cargo = roles[0]["role"] if roles else "?"
    print(f"  {row[0]:<35}  {cargo}")
print("  ...")

print("\n=== SAMPLE: 5 ELECTED DEPUTIES (DEPUTADO FEDERAL) ===")
for row in db.execute("""
    SELECT p.name, p.state, p.party, p.cpf, er.position
    FROM politicians p
    JOIN election_results er ON er.tse_seq_candidate = p.tse_id
    WHERE er.position = 'DEPUTADO FEDERAL'
    LIMIT 5
""").fetchall():
    print(f"  {row[0]:<35} {row[1]:<4} {row[2]:<8} CPF:{row[3]}")

print("\n=== CPF COVERAGE ===")
total    = db.execute("SELECT COUNT(*) FROM politicians").fetchone()[0]
with_cpf = db.execute("SELECT COUNT(*) FROM politicians WHERE cpf IS NOT NULL AND cpf != ''").fetchone()[0]
print(f"  Total politicians : {total:,}")
print(f"  With CPF          : {with_cpf:,}  ({with_cpf/total*100:.1f}%)")
print(f"  Without CPF       : {total - with_cpf:,}  (magistrados/CSV — no CPF in source)")
