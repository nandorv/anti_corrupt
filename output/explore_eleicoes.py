import pandas as pd

lines = []

# ── FILE 1: consulta_cand_2022_BRASIL.csv ────────────────────────────────────
f1 = 'eleicoes/consulta_cand_2022_BRASIL.csv'
df1 = pd.read_csv(f1, encoding='latin1', sep=';', low_memory=False)

elected1 = df1[df1['DS_SIT_TOT_TURNO'].str.contains('ELEITO', na=False)]

lines += [
    "=== FILE 1: consulta_cand_2022_BRASIL.csv (Eleições Gerais 2022) ===",
    f"  Total candidatos : {len(df1):,}",
    f"  ELEITOS          : {len(elected1):,}",
    "",
    "  DS_SIT_TOT_TURNO breakdown:",
]
for val, cnt in df1['DS_SIT_TOT_TURNO'].value_counts().items():
    lines.append(f"    {val:<35} {cnt:>6,}")

lines.append("\n  Cargos entre os ELEITOS:")
for cargo, cnt in elected1['DS_CARGO'].value_counts().items():
    lines.append(f"    {cargo:<35} {cnt:>5,}")

lines.append("\n  Amostra dos eleitos (5 primeiros):")
for _, r in elected1[['NM_CANDIDATO','SG_PARTIDO','DS_CARGO','SG_UF','DS_SIT_TOT_TURNO']].head(5).iterrows():
    lines.append(f"    {r['NM_CANDIDATO']:<40} | {r['SG_PARTIDO']:<8} | {r['DS_CARGO']:<22} | {r['SG_UF']} | {r['DS_SIT_TOT_TURNO']}")

# ── FILE 2: votacao_candidato_munzona_2024_BRASIL.csv ────────────────────────
f2 = 'eleicoes/votacao_candidato_munzona_2024_BRASIL.csv'
df2 = pd.read_csv(f2, encoding='latin1', sep=';', low_memory=False)

lines += [
    "",
    "=== FILE 2: votacao_candidato_munzona_2024_BRASIL.csv (Eleições Municipais 2024) ===",
    f"  Total rows : {len(df2):,}",
    f"  Columns    : {list(df2.columns)}",
    "",
]

sit_cols = [c for c in df2.columns if any(k in c for k in ('SITUAC','ELEITO','RESULT'))]
lines.append(f"  Election-result columns: {sit_cols}")

for col in sit_cols:
    lines.append(f"\n  [{col}] breakdown:")
    for val, cnt in df2[col].value_counts().items():
        lines.append(f"    {val:<45} {cnt:>8,}")

# Elected in file 2
if 'DS_SIT_TOT_TURNO' in df2.columns:
    elected2 = df2[df2['DS_SIT_TOT_TURNO'].str.contains('ELEITO', na=False)]
    lines += [
        "",
        f"  ELEITOS          : {len(elected2):,}",
        "  Cargos entre os ELEITOS:",
    ]
    for cargo, cnt in elected2['DS_CARGO'].value_counts().items():
        lines.append(f"    {cargo:<35} {cnt:>5,}")
    lines.append("\n  Amostra dos eleitos (5 primeiros):")
    for _, r in elected2[['NM_CANDIDATO','SG_PARTIDO','DS_CARGO','SG_UF','DS_SIT_TOT_TURNO']].head(5).iterrows():
        lines.append(f"    {r['NM_CANDIDATO']:<40} | {r['SG_PARTIDO']:<8} | {r['DS_CARGO']:<22} | {r['SG_UF']} | {r['DS_SIT_TOT_TURNO']}")

with open('output/eleicoes_summary.txt', 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(lines))
print("Written to output/eleicoes_summary.txt")
