"""
Receita Federal bulk data importer.

Downloads and imports the official Receita Federal open data dumps, which
contain FULL (unmasked) CPFs for company partners — enabling true CPF
cross-reference against our politicians table.

Files downloaded from:
    https://dadosabertos.rfb.gov.br/CNPJ/

Updated monthly (usually around the 10th). Total ~15GB uncompressed.
We download selectively:
    Socios*.zip        — QSA partner data with full CPFs  (~2 GB compressed)
    Empresas*.zip      — Company name, situation, opening date (~3 GB compressed)

Output:
    data/rf/socios.db  — SQLite with socios + empresas tables (import only
                         what we need; much smaller than full dump)

Usage:
    python scripts/import_rf_bulk.py --download   # download + import everything
    python scripts/import_rf_bulk.py --socios      # only socios (for CPF cross-ref)
    python scripts/import_rf_bulk.py --cross-ref   # cross-ref against our politicians
    python scripts/import_rf_bulk.py --status      # show what's already downloaded

After running --cross-ref, the companies table in history.db gets updated with
the self_dealing flag where a politician CPF matches a QSA partner CPF.
"""

import sys
import os
import re
import csv
import zipfile
import hashlib
import logging
import argparse
import datetime
import sqlite3
from pathlib import Path
from io import TextIOWrapper

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.history.store import HistoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RF_BASE = "https://dadosabertos.rfb.gov.br/CNPJ"
DATA_DIR = Path("data/rf")
RF_DB_PATH = DATA_DIR / "socios.db"

# RF file layout (fixed-width or pipe-delimited CSVs inside the ZIPs)
# Socios: CNPJ_BASICO|IDENTIFICADOR|NOME_SOCIO|CNPJ_CPF_SOCIO|QUALIFICACAO|...
# Empresas: CNPJ_BASICO|RAZAO_SOCIAL|NATUREZA_JURIDICA|QUALIFICACAO|CAPITAL_SOCIAL|PORTE|ENTE_FED_RESPONSAVEL
SOCIOS_COLS = [
    "cnpj_basico", "identificador", "nome_socio",
    "cnpj_cpf_socio", "qualificacao_socio", "data_entrada",
    "pais", "representante_legal", "nome_representante",
    "qualificacao_representante", "faixa_etaria",
]
EMPRESAS_COLS = [
    "cnpj_basico", "razao_social", "natureza_juridica",
    "qualificacao_responsavel", "capital_social", "porte", "ente_federativo",
]


def get_file_list(client: httpx.Client) -> list[dict]:
    """Scrape the RF directory listing for available ZIP files."""
    resp = client.get(f"{RF_BASE}/", timeout=30)
    resp.raise_for_status()
    # Simple regex to find .zip filenames in directory listing HTML
    pattern = r'href="([^"]+\.zip)"'
    files = re.findall(pattern, resp.text, re.IGNORECASE)
    return [{"name": f, "url": f"{RF_BASE}/{f}"} for f in files]


def download_file(url: str, dest: Path, client: httpx.Client) -> bool:
    """Stream-download a file, show progress. Returns True on success."""
    if dest.exists():
        logger.info("  Already downloaded: %s", dest.name)
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    logger.info("  Downloading %s ...", dest.name)
    try:
        with client.stream("GET", url, timeout=None) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        print(f"\r  {done/1024/1024:.0f} MB / {total/1024/1024:.0f} MB  ({pct:.0f}%)", end="", flush=True)
            print()
        tmp.rename(dest)
        logger.info("  Saved: %s (%.0f MB)", dest.name, dest.stat().st_size / 1024 / 1024)
        return True
    except Exception as exc:
        logger.error("  Download failed: %s", exc)
        if tmp.exists():
            tmp.unlink()
        return False


def ensure_rf_db() -> sqlite3.Connection:
    """Open (or create) the RF SQLite DB."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(RF_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS socios (
            cnpj_basico       TEXT,
            identificador     TEXT,
            nome_socio        TEXT,
            cnpj_cpf_socio    TEXT,   -- full 11 or 14 digits
            qualificacao      TEXT,
            data_entrada      TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            cnpj_basico   TEXT PRIMARY KEY,
            razao_social  TEXT,
            capital_social REAL,
            porte         TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_socios_cpf ON socios(cnpj_cpf_socio)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_socios_cnpj ON socios(cnpj_basico)")
    conn.commit()
    return conn


def import_socios_zip(zip_path: Path, rf_conn: sqlite3.Connection) -> int:
    """
    Import a Socios*.zip into the rf socios table.
    RF CSVs use ';' delimiter, latin-1 encoding, no header row.
    Returns row count imported.
    """
    imported = 0
    batch = []
    BATCH = 50_000

    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            logger.info("  Importing %s from %s ...", name, zip_path.name)
            with zf.open(name) as raw:
                reader = csv.reader(TextIOWrapper(raw, encoding="latin-1", errors="replace"),
                                    delimiter=";")
                for row in reader:
                    if len(row) < 4:
                        continue
                    cnpj_basico = row[0].strip().zfill(8)
                    identificador = row[1].strip()
                    nome = row[2].strip()
                    cpf_cnpj = re.sub(r"\D", "", row[3].strip())
                    qualificacao = row[4].strip() if len(row) > 4 else ""
                    data_entrada = row[5].strip() if len(row) > 5 else ""
                    batch.append((cnpj_basico, identificador, nome, cpf_cnpj,
                                  qualificacao, data_entrada))
                    imported += 1
                    if len(batch) >= BATCH:
                        rf_conn.executemany(
                            "INSERT OR IGNORE INTO socios VALUES (?,?,?,?,?,?)", batch
                        )
                        rf_conn.commit()
                        batch.clear()
                        logger.info("    ... %d rows", imported)

    if batch:
        rf_conn.executemany("INSERT OR IGNORE INTO socios VALUES (?,?,?,?,?,?)", batch)
        rf_conn.commit()

    logger.info("  Imported %d socios rows from %s", imported, zip_path.name)
    return imported


def import_empresas_zip(zip_path: Path, rf_conn: sqlite3.Connection) -> int:
    """Import an Empresas*.zip into the rf empresas table."""
    imported = 0
    batch = []
    BATCH = 50_000

    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            logger.info("  Importing %s from %s ...", name, zip_path.name)
            with zf.open(name) as raw:
                reader = csv.reader(TextIOWrapper(raw, encoding="latin-1", errors="replace"),
                                    delimiter=";")
                for row in reader:
                    if len(row) < 2:
                        continue
                    cnpj_basico = row[0].strip().zfill(8)
                    razao = row[1].strip()
                    capital = 0.0
                    try:
                        capital = float(row[4].replace(",", ".")) if len(row) > 4 else 0.0
                    except ValueError:
                        pass
                    porte = row[5].strip() if len(row) > 5 else ""
                    batch.append((cnpj_basico, razao, capital, porte))
                    imported += 1
                    if len(batch) >= BATCH:
                        rf_conn.executemany(
                            "INSERT OR REPLACE INTO empresas VALUES (?,?,?,?)", batch
                        )
                        rf_conn.commit()
                        batch.clear()

    if batch:
        rf_conn.executemany("INSERT OR REPLACE INTO empresas VALUES (?,?,?,?)", batch)
        rf_conn.commit()

    logger.info("  Imported %d empresas rows from %s", imported, zip_path.name)
    return imported


def cross_reference(store: HistoryStore, rf_conn: sqlite3.Connection) -> None:
    """
    Cross-reference politician CPFs against the RF socios table.
    Updates the self_dealing flag on matching companies in history.db.
    """
    import json

    # Load politician CPFs
    pol_rows = store._db.execute(
        "SELECT id, name, cpf FROM politicians WHERE cpf IS NOT NULL AND cpf != ''"
    ).fetchall()
    pol_by_cpf = {}
    for pol_id, name, cpf in pol_rows:
        clean = re.sub(r"\D", "", cpf)
        if len(clean) == 11:
            pol_by_cpf[clean] = {"id": pol_id, "name": name}
    logger.info("Loaded %d politician CPFs", len(pol_by_cpf))

    if not pol_by_cpf:
        logger.warning("No politician CPFs found — check TSE data was seeded")
        return

    # Find matches: politician CPF appears as QSA partner of a CNPJ
    logger.info("Querying RF socios table for matches...")
    cpf_list = list(pol_by_cpf.keys())
    # SQLite has a limit on IN clause size; chunk if needed
    CHUNK = 500
    hits = []
    for i in range(0, len(cpf_list), CHUNK):
        chunk = cpf_list[i:i+CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = rf_conn.execute(
            f"SELECT cnpj_basico, cnpj_cpf_socio, nome_socio FROM socios "
            f"WHERE cnpj_cpf_socio IN ({placeholders})",
            chunk
        ).fetchall()
        hits.extend(rows)

    logger.info("Found %d QSA matches for politician CPFs", len(hits))

    if not hits:
        logger.info("No self-dealing matches found.")
        return

    # Group by cnpj_basico
    from collections import defaultdict
    cnpj_to_pols: dict[str, list] = defaultdict(list)
    for cnpj_basico, cpf, nome_socio in hits:
        pol = pol_by_cpf.get(cpf)
        if pol:
            cnpj_to_pols[cnpj_basico].append({
                "politician_id": pol["id"],
                "politician_name": pol["name"],
                "cpf": cpf,
                "rf_name": nome_socio,
            })

    # Update companies table: add self_dealing flag and note the politician(s)
    updated = 0
    for cnpj_basico, pols in cnpj_to_pols.items():
        # Match against our companies: CNPJ has 14 digits = basico(8) + ordem(4) + dv(2)
        # We need to find companies where cnpj starts with cnpj_basico
        company_rows = store._db.execute(
            "SELECT cnpj, flags, socios FROM companies WHERE cnpj LIKE ?",
            [f"{cnpj_basico}%"]
        ).fetchall()
        for cnpj, flags_json, socios_json in company_rows:
            flags = json.loads(flags_json or "[]")
            if "self_dealing" not in flags:
                flags.append("self_dealing")
            socios = json.loads(socios_json or "[]") if socios_json else []
            # Annotate socios with match
            for pol_hit in pols:
                existing = next((s for s in socios if s.get("cpf_cnpj_socio") == pol_hit["cpf"]), None)
                if existing:
                    existing["matched_politician"] = pol_hit["politician_id"]
                else:
                    socios.append({
                        "nome": pol_hit["rf_name"],
                        "cpf_cnpj_socio": pol_hit["cpf"],
                        "qualificacao_socio": "(RF bulk match)",
                        "matched_politician": pol_hit["politician_id"],
                    })
            store._db.execute(
                "UPDATE companies SET flags=?, socios=? WHERE cnpj=?",
                [json.dumps(flags), json.dumps(socios, ensure_ascii=False), cnpj]
            )
            updated += 1
            logger.info("  🚩 SELF_DEALING: %s — %s",
                        cnpj, " + ".join(p["politician_name"] for p in pols))

    store._db.conn.commit() if hasattr(store._db, "conn") else store._db.execute("SELECT 1")
    logger.info("Updated %d company records with self_dealing flag", updated)

    # Summary
    print(f"\n{'='*60}")
    print(f"SELF-DEALING HITS: {updated} companies")
    for cnpj_basico, pols in sorted(cnpj_to_pols.items()):
        total = store._db.execute(
            "SELECT SUM(total_received_ceap) FROM companies WHERE cnpj LIKE ?",
            [f"{cnpj_basico}%"]
        ).fetchone()[0] or 0
        for p in pols:
            print(f"  {cnpj_basico}*  R${total:>12,.2f}  {p['politician_name']} ({p['politician_id']})")
    print()


def show_status() -> None:
    """Show what RF files are already downloaded."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = list(DATA_DIR.glob("*.zip"))
    if not files:
        print("No RF files downloaded yet.")
        print(f"Run with --download to fetch from {RF_BASE}/")
        return
    print(f"\nDownloaded RF files in {DATA_DIR}:")
    for f in sorted(files):
        print(f"  {f.name:<40} {f.stat().st_size/1024/1024:>8.0f} MB")
    if RF_DB_PATH.exists():
        conn = sqlite3.connect(str(RF_DB_PATH))
        socios_count = conn.execute("SELECT COUNT(*) FROM socios").fetchone()[0]
        empresas_count = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        print(f"\nRF SQLite DB ({RF_DB_PATH}):")
        print(f"  socios:   {socios_count:>12,}")
        print(f"  empresas: {empresas_count:>12,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Receita Federal bulk data importer")
    parser.add_argument("--download", action="store_true",
                        help="Download Socios + Empresas ZIPs and import into local DB")
    parser.add_argument("--socios", action="store_true",
                        help="Download + import only Socios ZIPs (for CPF cross-ref)")
    parser.add_argument("--empresas", action="store_true",
                        help="Download + import only Empresas ZIPs")
    parser.add_argument("--cross-ref", action="store_true",
                        help="Cross-reference politician CPFs against imported RF data")
    parser.add_argument("--status", action="store_true",
                        help="Show download status")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    want_socios = args.download or args.socios
    want_empresas = args.download or args.empresas

    if not any([want_socios, want_empresas, args.cross_ref]):
        parser.print_help()
        return

    if args.cross_ref and not RF_DB_PATH.exists():
        logger.error("RF DB not found. Run --socios first to import the data.")
        sys.exit(1)

    if args.cross_ref:
        store = HistoryStore()
        rf_conn = sqlite3.connect(str(RF_DB_PATH))
        cross_reference(store, rf_conn)
        return

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0"},
        timeout=60,
        follow_redirects=True,
    ) as client:
        logger.info("Fetching RF file listing from %s ...", RF_BASE)
        try:
            all_files = get_file_list(client)
        except Exception as exc:
            logger.error("Failed to fetch RF listing: %s", exc)
            # Fallback: known pattern — files are named Socios0.zip ... Socios9.zip etc.
            all_files = []
            for kind in ["Socios", "Empresas"]:
                for i in range(10):
                    all_files.append({
                        "name": f"{kind}{i}.zip",
                        "url": f"{RF_BASE}/{kind}{i}.zip",
                    })
            logger.info("Using fallback file list (%d files)", len(all_files))

        socios_files = [f for f in all_files if "ocio" in f["name"]]
        empresas_files = [f for f in all_files if "mpresa" in f["name"] or "Empresa" in f["name"]]

        logger.info("Found %d Socios files, %d Empresas files",
                    len(socios_files), len(empresas_files))

        rf_conn = ensure_rf_db()

        if want_socios:
            logger.info("=== Downloading Socios (partner/CPF data) ===")
            for f in socios_files:
                dest = DATA_DIR / f["name"]
                if download_file(f["url"], dest, client):
                    # Check if already imported
                    count = rf_conn.execute(
                        "SELECT COUNT(*) FROM socios"
                    ).fetchone()[0]
                    if count == 0 or not (DATA_DIR / f"{f['name']}.imported").exists():
                        import_socios_zip(dest, rf_conn)
                        (DATA_DIR / f"{f['name']}.imported").touch()

        if want_empresas:
            logger.info("=== Downloading Empresas (company names/status) ===")
            for f in empresas_files:
                dest = DATA_DIR / f["name"]
                if download_file(f["url"], dest, client):
                    count = rf_conn.execute(
                        "SELECT COUNT(*) FROM empresas"
                    ).fetchone()[0]
                    if count == 0 or not (DATA_DIR / f"{f['name']}.imported").exists():
                        import_empresas_zip(dest, rf_conn)
                        (DATA_DIR / f"{f['name']}.imported").touch()

    rf_conn.close()
    show_status()

    if want_socios:
        logger.info(
            "\nNow run:  python scripts/import_rf_bulk.py --cross-ref\n"
            "to flag self-dealing companies in history.db"
        )


if __name__ == "__main__":
    main()
