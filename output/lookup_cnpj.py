"""
CNPJ enrichment script.

For every distinct CNPJ in the expenses table, fetch company data from
BrasilAPI (Receita Federal mirror) and store in the `companies` table.
Then cross-reference QSA (company owners) CPFs against politician CPFs
to flag self-dealing, and apply a set of other anti-corruption heuristics.

Usage:
    python output/lookup_cnpj.py                # all CNPJs not yet fetched
    python output/lookup_cnpj.py --refetch      # re-fetch everything
    python output/lookup_cnpj.py --limit 100    # stop after 100 CNPJs
    python output/lookup_cnpj.py --report       # print findings, no fetch

Flags set on CompanyProfile:
    self_dealing         — QSA owner CPF matches a politician CPF
    recently_opened      — opened < 6 months before first CEAP payment
    inactive             — situacao_cadastral in INAPTA | BAIXADA | SUSPENSA
    high_value           — total received > R$100k
    shared_supplier      — appears in cabinets of 5+ different deputies
"""

import sys
import os
import json
import time
import argparse
import datetime
import logging

import httpx

sys.path.insert(0, ".")
from src.history.store import HistoryStore
from src.history.models import CompanyProfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BRASILAPI_BASE = "https://brasilapi.com.br/api/cnpj/v1"
DELAY = 0.6          # seconds between requests (BrasilAPI is generous but rate-limit exists)
DELAY_ON_429 = 30    # back-off on rate limit
DELAY_ON_ERROR = 5
HIGH_VALUE_THRESHOLD = 100_000.0
SHARED_SUPPLIER_THRESHOLD = 5  # 5+ different deputies


def clean_cnpj(raw: str) -> str:
    """Strip non-digits from CNPJ."""
    return "".join(c for c in (raw or "") if c.isdigit())


def parse_date(s: str) -> datetime.date | None:
    """Parse various date strings to date object, return None on failure."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def is_valid_cnpj(cnpj: str) -> bool:
    """Basic sanity check — reject obvious placeholders like 00000000000001 or all-same-digit."""
    if len(cnpj) != 14:
        return False
    # All same digit (e.g. 00000000000000, 11111111111111)
    if len(set(cnpj)) == 1:
        return False
    # Known placeholder patterns used by deputies for cash/no-CNPJ expenses
    PLACEHOLDERS = {"00000000000001", "11111111111191", "00000000000191"}
    if cnpj in PLACEHOLDERS:
        return False
    return True


def fetch_cnpj(cnpj: str, client: httpx.Client) -> dict | None:
    """
    Fetch CNPJ data from BrasilAPI.
    Returns:
      dict  — success (may be empty {} if 404/400/422 = not found)
      None  — transient error, should retry
    """
    url = f"{BRASILAPI_BASE}/{cnpj}"
    try:
        resp = client.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (404, 400, 422):
            # 404 = not in Receita Federal; 400/422 = invalid or unregistered CNPJ
            logger.debug("CNPJ %s not found (%d)", cnpj, resp.status_code)
            return {}   # empty dict = not found, skip retry, store stub
        if resp.status_code == 429:
            logger.warning("Rate limited — sleeping %ds", DELAY_ON_429)
            time.sleep(DELAY_ON_429)
            return None  # None = retry
        if resp.status_code >= 500:
            logger.warning("CNPJ %s server error %d", cnpj, resp.status_code)
            return None  # retry on 5xx
        logger.warning("CNPJ %s unexpected HTTP %d — skipping", cnpj, resp.status_code)
        return {}  # treat unknown 4xx as not-found, don't retry
    except httpx.TimeoutException:
        logger.warning("CNPJ %s timeout", cnpj)
        return None  # retry
    except Exception as exc:
        logger.warning("CNPJ %s fetch error: %s", cnpj, exc)
        return None


def build_flags(
    data: dict,
    total_received: float,
    num_deputies: int,
    first_expense_date: str | None,
    politician_cpfs: set[str],
) -> list[str]:
    """Derive anti-corruption flags from company data."""
    flags = []

    situacao = (data.get("descricao_situacao_cadastral") or
                data.get("situacao_cadastral") or "").upper()
    if situacao in ("INAPTA", "BAIXADA", "SUSPENSA", "NULA"):
        flags.append("inactive")

    data_abertura = parse_date(data.get("data_inicio_atividade") or data.get("data_abertura") or "")
    first_expense = parse_date(first_expense_date or "")
    if data_abertura and first_expense:
        delta_months = (first_expense.year - data_abertura.year) * 12 + \
                       (first_expense.month - data_abertura.month)
        if 0 <= delta_months < 6:
            flags.append("recently_opened")

    if total_received >= HIGH_VALUE_THRESHOLD:
        flags.append("high_value")

    if num_deputies >= SHARED_SUPPLIER_THRESHOLD:
        flags.append("shared_supplier")

    # QSA owner CPF cross-reference against politicians
    socios = data.get("qsa") or []
    for socio in socios:
        cpf_raw = socio.get("cpf_representante_legal") or socio.get("cnpj_cpf_do_socio") or ""
        cpf_clean = clean_cnpj(cpf_raw)
        if cpf_clean and len(cpf_clean) == 11 and cpf_clean in politician_cpfs:
            flags.append("self_dealing")
            break  # one hit is enough to flag

    return sorted(set(flags))


def build_company(cnpj: str, data: dict, total_received: float,
                  paid_by_deputies: list[str], flags: list[str]) -> CompanyProfile:
    """Map BrasilAPI response → CompanyProfile model."""
    # BrasilAPI field names vary slightly between endpoints/versions
    razao = (data.get("razao_social") or data.get("nome") or "").strip()
    fantasia = (data.get("nome_fantasia") or "").strip() or None
    situacao = (data.get("descricao_situacao_cadastral") or
                data.get("situacao_cadastral") or "").upper() or None
    abertura = (data.get("data_inicio_atividade") or
                data.get("data_abertura") or "").strip() or None
    if abertura:
        d = parse_date(abertura)
        abertura = d.isoformat() if d else None

    municipio = (data.get("municipio") or "").strip() or None
    uf = (data.get("uf") or "").strip() or None
    capital = data.get("capital_social")

    # Atividade principal
    atv = data.get("cnae_fiscal_descricao") or data.get("atividade_principal")
    if isinstance(atv, list):
        atv = json.dumps(atv, ensure_ascii=False)
    elif atv:
        atv = str(atv)

    # QSA / socios
    socios_raw = data.get("qsa") or []
    socios_clean = []
    for s in socios_raw:
        socios_clean.append({
            "nome": s.get("nome_socio") or s.get("nome") or "",
            "cpf_cnpj_socio": s.get("cpf_representante_legal") or s.get("cnpj_cpf_do_socio") or "",
            "qualificacao_socio": s.get("qualificacao_socio") or s.get("qualificacao_representante_legal") or "",
        })

    return CompanyProfile(
        cnpj=cnpj,
        razao_social=razao,
        nome_fantasia=fantasia,
        situacao_cadastral=situacao,
        data_abertura=abertura,
        atividade_principal=atv,
        municipio=municipio,
        uf=uf,
        capital_social=float(capital) if capital is not None else None,
        socios=json.dumps(socios_clean, ensure_ascii=False) if socios_clean else None,
        flags=flags,
        paid_by_deputies=paid_by_deputies,
        total_received_ceap=total_received,
    )


def print_report(store: HistoryStore) -> None:
    """Print a summary of flagged companies."""
    total = store.count_companies()
    flagged = store.flagged_companies()
    print(f"\n{'='*60}")
    print(f"COMPANIES IN DB: {total:,}")
    print(f"FLAGGED:         {len(flagged):,}")
    print(f"{'='*60}")

    by_flag: dict[str, list] = {}
    for c in flagged:
        for f in c["flags"]:
            by_flag.setdefault(f, []).append(c)

    for flag, companies in sorted(by_flag.items()):
        print(f"\n🚩 {flag.upper()} ({len(companies)} companies)")
        for c in sorted(companies, key=lambda x: x["total_received_ceap"], reverse=True)[:10]:
            print(f"   {c['cnpj']}  R${c['total_received_ceap']:>12,.2f}  "
                  f"{c['situacao_cadastral'] or '?':10s}  {c['razao_social'][:50]}")
        if len(companies) > 10:
            print(f"   ... and {len(companies)-10} more")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich CEAP expenses with CNPJ data")
    parser.add_argument("--refetch", action="store_true",
                        help="Re-fetch all CNPJs, even if already in DB")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after this many CNPJs (0 = no limit)")
    parser.add_argument("--report", action="store_true",
                        help="Print findings report only, no fetching")
    args = parser.parse_args()

    store = HistoryStore()

    if args.report:
        print_report(store)
        return

    # ── Gather distinct CNPJs from expenses ──────────────────────────────
    rows = store._db.execute(
        "SELECT supplier_cnpj_cpf, MIN(year || '-' || printf('%02d', month)) as first_date, "
        "       SUM(value) as total, COUNT(DISTINCT deputy_id) as num_deputies, "
        "       GROUP_CONCAT(DISTINCT deputy_id) as deputy_ids "
        "FROM expenses "
        "WHERE supplier_cnpj_cpf IS NOT NULL AND supplier_cnpj_cpf != '' "
        "GROUP BY supplier_cnpj_cpf"
    ).fetchall()

    logger.info("Found %d distinct supplier CNPJs/CPFs in expenses", len(rows))

    # Only 14-digit strings are CNPJs (11-digit = CPF of individuals, skip)
    cnpj_data = []
    for raw_cnpj, first_date, total, num_dep, dep_ids in rows:
        clean = clean_cnpj(raw_cnpj)
        if len(clean) != 14:
            continue  # skip CPF-type suppliers (individuals)
        cnpj_data.append({
            "cnpj": clean,
            "first_date": first_date,
            "total": float(total or 0),
            "num_deputies": int(num_dep or 0),
            "deputy_ids": (dep_ids or "").split(","),
        })

    logger.info("  → %d are CNPJs (companies, 14-digit)", len(cnpj_data))

    # Filter obviously invalid / placeholder CNPJs before hitting the API
    before_valid = len(cnpj_data)
    cnpj_data = [c for c in cnpj_data if is_valid_cnpj(c["cnpj"])]
    skipped_invalid = before_valid - len(cnpj_data)
    if skipped_invalid:
        logger.info("  → %d invalid/placeholder CNPJs skipped", skipped_invalid)

    # Filter out already-fetched CNPJs unless --refetch
    if not args.refetch:
        already = {r[0] for r in store._db.execute(
            "SELECT cnpj FROM companies"
        ).fetchall()}
        before = len(cnpj_data)
        cnpj_data = [c for c in cnpj_data if c["cnpj"] not in already]
        logger.info("  → %d new (skipping %d already in DB)", len(cnpj_data), before - len(cnpj_data))

    if args.limit:
        cnpj_data = cnpj_data[:args.limit]
        logger.info("  → Limited to %d", args.limit)

    if not cnpj_data:
        logger.info("Nothing to fetch. Run with --refetch to re-process or --report to view findings.")
        return

    # ── Load politician CPFs for cross-reference ─────────────────────────
    pol_cpf_rows = store._db.execute(
        "SELECT cpf FROM politicians WHERE cpf IS NOT NULL AND cpf != ''"
    ).fetchall()
    politician_cpfs = {clean_cnpj(r[0]) for r in pol_cpf_rows if r[0]}
    logger.info("Loaded %d politician CPFs for cross-reference", len(politician_cpfs))

    # ── Fetch loop ────────────────────────────────────────────────────────
    batch: list[CompanyProfile] = []
    BATCH_SIZE = 50
    fetched = skipped = flagged_count = 0

    with httpx.Client(headers={"User-Agent": "anti-corrupt-research/1.0"}) as client:
        for i, item in enumerate(cnpj_data, 1):
            cnpj = item["cnpj"]
            logger.info("[%d/%d] %s", i, len(cnpj_data), cnpj)

            data = None
            for attempt in range(3):
                data = fetch_cnpj(cnpj, client)
                if data is not None:
                    break
                time.sleep(DELAY_ON_ERROR * (attempt + 1))

            if data is None:
                logger.warning("  Giving up on %s after 3 attempts", cnpj)
                skipped += 1
                continue

            if not data:
                # 404 — company not found; store minimal stub so we don't retry
                batch.append(CompanyProfile(
                    cnpj=cnpj,
                    razao_social="(não encontrado)",
                    total_received_ceap=item["total"],
                    paid_by_deputies=item["deputy_ids"],
                ))
                fetched += 1
            else:
                flags = build_flags(
                    data=data,
                    total_received=item["total"],
                    num_deputies=item["num_deputies"],
                    first_expense_date=item["first_date"],
                    politician_cpfs=politician_cpfs,
                )
                company = build_company(
                    cnpj=cnpj,
                    data=data,
                    total_received=item["total"],
                    paid_by_deputies=item["deputy_ids"],
                    flags=flags,
                )
                batch.append(company)
                fetched += 1
                if flags:
                    flagged_count += 1
                    logger.info("  🚩 %s  flags=%s  R$%.0f  %s",
                                cnpj, flags, item["total"],
                                data.get("razao_social", "")[:40])

            # Flush batch
            if len(batch) >= BATCH_SIZE:
                store.upsert_companies(batch)
                logger.info("  💾 Saved batch of %d (total fetched: %d)", len(batch), fetched)
                batch.clear()

            time.sleep(DELAY)

    # Final flush
    if batch:
        store.upsert_companies(batch)

    logger.info(
        "\n✅ Done: %d fetched, %d skipped, %d flagged",
        fetched, skipped, flagged_count,
    )
    print_report(store)


if __name__ == "__main__":
    main()
