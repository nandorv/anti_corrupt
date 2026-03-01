"""Analyze the two election CSV files and print a summary."""
import os, sys
from collections import defaultdict

PATH1 = 'eleicoes/consulta_cand_2022_BRASIL.csv'
PATH2 = 'eleicoes/votacao_candidato_munzona_2024_BRASIL.csv'

# ── FILE 1: 2022 federal + state elections ──────────────────────────────────
print("=== FILE 1: consulta_cand_2022_BRASIL.csv (2022 elections) ===", flush=True)

status_counts = defaultdict(int)
role_elected  = defaultdict(int)
total = 0

with open(PATH1, encoding='latin1') as f:
    raw_header = f.readline().strip().split(';')
    header = [h.strip('"') for h in raw_header]
    cargo_idx  = header.index('DS_CARGO')
    status_idx = header.index('DS_SIT_TOT_TURNO')

    for line in f:
        parts = line.strip().split(';')
        if len(parts) <= status_idx:
            continue
        total += 1
        status = parts[status_idx].strip('"')
        status_counts[status] += 1
        if 'ELEITO' in status and status != 'NÃO ELEITO':
            cargo = parts[cargo_idx].strip('"')
            role_elected[cargo] += 1

print(f"Total candidate rows: {total}")
print("\nAll outcome statuses:")
for s, c in sorted(status_counts.items(), key=lambda x: -x[1]):
    print(f"  {s:<40} {c:>6}")
print("\nElected by role (DS_CARGO) [includes ELEITO / ELEITO POR QP / ELEITO POR MÉDIA]:")
for r, c in sorted(role_elected.items(), key=lambda x: -x[1]):
    print(f"  {r:<40} {c:>6}")
print(f"\nTotal elected (file 1): {sum(role_elected.values())}")

# ── FILE 2: 2024 municipal elections ───────────────────────────────────────
print("\n=== FILE 2: votacao_candidato_munzona_2024_BRASIL.csv (2024 elections) ===", flush=True)

status2   = defaultdict(int)
role2     = defaultdict(int)
total2    = 0
seen_cands = set()  # (NM_CANDIDATO, SG_PARTIDO) deduped

with open(PATH2, encoding='latin1') as f:
    raw_header2 = f.readline().strip().split(';')
    header2 = [h.strip('"') for h in raw_header2]
    print(f"Columns: {header2}", flush=True)

    # locate key columns
    try:
        cargo_idx2  = header2.index('DS_CARGO')
        name_idx2   = header2.index('NM_CANDIDATO')
        party_idx2  = header2.index('SG_PARTIDO')
        status_idx2 = header2.index('DS_SIT_TOT_TURNO')
    except ValueError as e:
        print(f"Missing column: {e}")
        sys.exit(1)

    for line in f:
        parts = line.strip().split(';')
        if len(parts) <= status_idx2:
            continue
        total2 += 1
        status = parts[status_idx2].strip('"')
        status2[status] += 1
        if 'ELEITO' in status and status != 'NÃO ELEITO':
            cargo = parts[cargo_idx2].strip('"')
            role2[cargo] += 1
            key = (parts[name_idx2].strip('"'), parts[party_idx2].strip('"'))
            seen_cands.add(key)

print(f"Total vote rows: {total2}")
print("\nAll outcome statuses:")
for s, c in sorted(status2.items(), key=lambda x: -x[1]):
    print(f"  {s:<40} {c:>8}")
print("\nElected by role:")
for r, c in sorted(role2.items(), key=lambda x: -x[1]):
    print(f"  {r:<40} {c:>8}")
print(f"\nUnique elected politicians (file 2): {len(seen_cands)}")
print(f"Total elected rows (file 2): {sum(role2.values())}")
print("\nDONE", flush=True)
