"""
Seed DB with all elected politicians from TSE consulta_cand CSV files.

  eleicoes/consulta_cand_2022_BRASIL.csv  — 2022 federal + state elections
  eleicoes/consulta_cand_2024_BRASIL.csv  — 2024 municipal elections

Both files have the same 50-column format with CPF and birth date included.
"""
import sys, csv, os
sys.path.insert(0, ".")
csv.field_size_limit(10_000_000)

from src.history.store import HistoryStore
from src.history.models import Politician, PoliticianRole, ElectionResult

ELECTED = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}
SKIP_CARGO = {"VEREADOR"}

CARGO_META = {
    "DEPUTADO FEDERAL":   ("Deputado Federal",         "camara_dos_deputados",     "2023-02-01", "2027-01-31"),
    "DEPUTADO ESTADUAL":  ("Deputado Estadual",        "assembleia_legislativa",   "2023-01-01", "2026-12-31"),
    "DEPUTADO DISTRITAL": ("Deputado Distrital",       "camara_legislativa_df",    "2023-01-01", "2026-12-31"),
    "SENADOR":            ("Senador",                  "senado_federal",           "2023-02-01", "2031-01-31"),
    "GOVERNADOR":         ("Governador",               "governo_estadual",         "2023-01-01", "2026-12-31"),
    "VICE-GOVERNADOR":    ("Vice-Governador",          "governo_estadual",         "2023-01-01", "2026-12-31"),
    "1º SUPLENTE":        ("1º Suplente Senado",       "senado_federal",           "2023-02-01", None),
    "2º SUPLENTE":        ("2º Suplente Senado",       "senado_federal",           "2023-02-01", None),
    "PRESIDENTE":         ("Presidente da República",  "presidencia_da_republica", "2023-01-01", "2026-12-31"),
    "VICE-PRESIDENTE":    ("Vice-Presidente",          "presidencia_da_republica", "2023-01-01", "2026-12-31"),
    "PREFEITO":           ("Prefeito",                 "prefeitura_municipal",     "2025-01-01", "2028-12-31"),
    "VEREADOR":           ("Vereador",                 "camara_municipal",         "2025-01-01", "2028-12-31"),
}

MANDATE_BY_YEAR = {2022: ("2023-01-01", "2026-12-31"), 2024: ("2025-01-01", "2028-12-31")}

def _get(row, idx, col):
    i = idx.get(col)
    return row[i].strip('"') if i is not None and i < len(row) else ""

def _null(val):
    return None if val in ("#NULO", "", "#NE") else val

def parse_file(path, year):
    politicians, results, seen, skipped = [], [], set(), 0
    default_start, default_end = MANDATE_BY_YEAR.get(year, ("2023-01-01", None))
    source_tag = f"tse:consulta_cand_{year}"

    with open(path, encoding="latin1", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        headers = [h.strip('"') for h in next(reader)]
        idx = {h: i for i, h in enumerate(headers)}

        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error:
                skipped += 1
                continue

            if _get(row, idx, "DS_SIT_TOT_TURNO") not in ELECTED:
                continue
            if _get(row, idx, "DS_CARGO") in SKIP_CARGO:
                continue
            seq = _get(row, idx, "SQ_CANDIDATO")
            if seq in seen:
                continue
            seen.add(seq)

            name       = _get(row, idx, "NM_CANDIDATO")
            party      = _get(row, idx, "SG_PARTIDO")
            uf         = _get(row, idx, "SG_UF")
            cargo      = _get(row, idx, "DS_CARGO")
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
            role = PoliticianRole(
                role=meta[0] if meta else cargo,
                institution=meta[1] if meta else "desconhecida",
                start_date=meta[2] if meta else default_start,
                end_date=meta[3] if meta else default_end,
                notes=municipio if year == 2024 else None,
            )
            tags = [cargo, str(year), "eleito"]
            if municipio and year == 2024:
                tags.append(municipio)

            politicians.append(Politician(
                id=f"tse:{seq}", name=name, party=party, state=uf,
                birth_date=birth_date, tse_id=seq, cpf=cpf,
                roles=[role], tags=tags, sources=[source_tag],
            ))
            results.append(ElectionResult(
                year=year, state=uf,
                municipality=municipio if year == 2024 else None,
                position=cargo, candidate_name=name, candidate_number=nr,
                candidate_cpf=cpf, party=party, coalition=colig,
                elected=True, round=int(turno) if turno.isdigit() else 1,
                tse_seq_candidate=seq,
            ))

    if skipped:
        print(f"   ⚠ {skipped} malformed rows skipped", flush=True)
    return politicians, results

# ── Run ───────────────────────────────────────────────────────────────────────
db_path = "output/history.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print("🗑  Dropped old DB", flush=True)

store = HistoryStore()

for year, path in [(2022, "eleicoes/consulta_cand_2022_BRASIL.csv"),
                   (2024, "eleicoes/consulta_cand_2024_BRASIL.csv")]:
    print(f"📥 {year}  ({path})...", flush=True)
    pols, res = parse_file(path, year)
    print(f"   {len(pols):,} elected found", flush=True)
    saved_p = store.upsert_politicians(pols)
    saved_r = store.upsert_election_results(res)
    with_cpf = sum(1 for p in pols if p.cpf)
    print(f"   ✓ {saved_p:,} politicians ({with_cpf:,} with CPF) | {saved_r:,} results", flush=True)

print("\n" + "="*50 + "\nFINAL DB STATS:")
for k, v in store.stats().items():
    print(f"  {k:<25} {v:>10,}")
print("="*50 + "\nDONE", flush=True)
