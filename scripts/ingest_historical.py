"""
Historical news-archive ingestion — three complementary sources.

Sources
-------
1. **Querido Diário** — full-text search over Brazilian official gazettes
   (appointments, contracts, spending).  Goes back years.
   API: GET https://queridodiario.ok.org.br/api/gazettes
2. **GDELT DOC 2.0**  — global news index with full-text article search.
   Rolling 3-month window only, but great for recent coverage.
   API: GET https://api.gdeltproject.org/api/v2/doc/doc
3. **Wayback CDX**     — Internet Archive URL index for major Brazilian
   news outlets.  10-15+ years of archived URLs; we regex-filter for
   politician name-slugs in the URL path.
   API: GET https://web.archive.org/cdx/search/cdx

Every result is entity-linked to politicians already in the DB and
written to the shared ``news_items`` table.

Usage
-----
    python scripts/ingest_historical.py                    # all sources, top 100
    python scripts/ingest_historical.py --source querido   # only Querido Diário
    python scripts/ingest_historical.py --source gdelt     # only GDELT
    python scripts/ingest_historical.py --source wayback   # only Wayback CDX
    python scripts/ingest_historical.py --politician "Lula"
    python scripts/ingest_historical.py --top 50           # top 50 by CEAP spend
    python scripts/ingest_historical.py --notable           # famous/investigated politicians
    python scripts/ingest_historical.py --all               # ALL deputies + STF + STJ + senators + ministers
    python scripts/ingest_historical.py --keywords          # corruption keyword search
    python scripts/ingest_historical.py --from-year 2015 --to-year 2025
    python scripts/ingest_historical.py --report           # stats
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.history.store import HistoryStore
from src.history.models import NewsItem

class _TqdmHandler(logging.StreamHandler):
    """Route log messages through tqdm.write() so the progress bar survives."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)

_handler = _TqdmHandler(sys.stderr)
_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
))
logging.root.setLevel(logging.INFO)
logging.root.handlers = [_handler]

# Silence noisy httpx request logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

log = logging.getLogger("historical")


# ======================================================================
# Constants
# ======================================================================

QUERIDO_BASE = "https://queridodiario.ok.org.br/api"
GDELT_BASE   = "https://api.gdeltproject.org/api/v2/doc/doc"
CDX_BASE     = "http://web.archive.org/cdx/search/cdx"

# Querido Diário themes relevant to corruption/public spending
QD_THEMES = [
    "licitacoes_e_contratos",  # bids & contracts
]

# Major Brazilian news domains whose /politics/ sections go back 10+ yrs
WAYBACK_DOMAINS = [
    ("www1.folha.uol.com.br/poder/",           "Folha Poder"),
    ("g1.globo.com/politica/",                  "G1 Política"),
    ("politica.estadao.com.br/",                "Estadão Política"),
    ("www.bbc.com/portuguese/articles/",        "BBC Brasil"),
    ("noticias.uol.com.br/politica/",           "UOL Política"),
    ("congressoemfoco.uol.com.br/",             "Congresso em Foco"),
    ("www.poder360.com.br/",                    "Poder360"),
    ("www.correiobraziliense.com.br/politica/", "Correio Braziliense"),
]

# Polite delays (seconds) between requests per source
DELAY_QD      = 1.0
DELAY_GDELT   = 1.5
DELAY_WAYBACK = 1.5

# Per-politician caps
QD_MAX_RESULTS      = 200   # max gazette hits per politician
GDELT_MAX_RESULTS   = 250   # API hard cap
WAYBACK_MAX_PER_DOM = 100   # max unique URLs per domain per politician

# Notable Brazilian politicians who are newsworthy enough to appear in
# article URLs.  Map: DB name fragment → preferred CDX search slug.
# These override the auto-generated slug so we get single-word matches
# that catch more articles (e.g. "lula" instead of "lula.+silva").
NOTABLE_POLITICIANS: list[tuple[str, str]] = [
    # (DB name fragment for LIKE match, CDX slug override)
    # Presidents / ex-presidents
    ("LUIZ INÁCIO LULA",      "lula"),
    ("BOLSONARO",             "bolsonaro"),
    # Key Congress leaders
    ("Arthur Lira",           "arthur-lira"),
    ("Aécio Neves",           "aecio"),
    ("RENAN.*CALHEIROS",      "calheiros"),
    ("Roseana Sarney",        "sarney"),
    ("SERGIO.*MORO",          "moro"),
    # Deputies flagged in CEAP who are also investigated
    ("Josimar Maranhãozinho", "maranhaozinho"),
    ("Silas Câmara",          "silas-camara"),
    ("Eunício Oliveira",      "eunicio"),
    ("Delegado Éder Mauro",   "eder-mauro"),
    ("Domingos Neto",         "domingos-neto"),
    ("Giacobo",               "giacobo"),
    ("Rubens Pereira",        "rubens-pereira"),
    ("Moses Rodrigues",       "moses-rodrigues"),
    ("Cleber Verde",          "cleber-verde"),
    ("Átila Lins",            "atila-lins"),
]

# Institutions to query for --all mode (deputies, senators, STF, STJ, ministers)
ALL_INSTITUTIONS = [
    "camara_dos_deputados",
    "senado_federal",
    "supremo_tribunal_federal",
    "superior_tribunal_justica",
    "governo_federal",
    "presidencia_da_republica",
]

# Corruption-related URL keywords.  We search each domain for URLs
# containing these terms to find articles about corruption, investigations,
# operations, etc. — regardless of specific politician names.
CORRUPTION_KEYWORDS: list[tuple[str, str]] = [
    ("corrupcao",        "Corrupção"),
    ("operacao-",        "Operação (police ops)"),
    ("policia-federal",  "Polícia Federal"),
    ("lava-jato",        "Lava Jato"),
    ("propina",          "Propina"),
    ("desvio",           "Desvio de verba"),
    ("delacao",          "Delação premiada"),
    ("lavagem",          "Lavagem de dinheiro"),
    ("peculato",         "Peculato"),
    ("caixa-dois",       "Caixa dois"),
    ("improbidade",      "Improbidade"),
    ("mensalao",         "Mensalão"),
    ("superfaturamento", "Superfaturamento"),
    ("fraude",           "Fraude"),
    ("cpi",              "CPI"),
]


# ======================================================================
# Shared helpers
# ======================================================================

def _normalize(text: str) -> str:
    """Lowercase + strip accents."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _slug(text: str) -> str:
    """Turn a name into a URL-slug-like string for CDX regex filtering."""
    s = _normalize(text)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _url_hash(url: str) -> str:
    return "news:" + hashlib.sha1(url.encode()).hexdigest()[:12]


def select_focus_politicians(
    store: HistoryStore,
    politician_name: Optional[str] = None,
    top_n: int = 100,
    notable_only: bool = False,
    all_institutions: bool = False,
) -> list[dict]:
    """
    Return a list of dicts {id, name, slug} for politicians to search.

    Priority order:
    1. Explicit --politician name → exact match (top 5 results)
    2. --all → ALL deputies, senators, STF, STJ & ministers from DB
    3. --notable → well-known politicians with slug overrides
    4. Otherwise: top N deputies by total CEAP expense amount
    """
    db = store._db

    if politician_name:
        rows = db.execute(
            "SELECT id, name FROM politicians "
            "WHERE name LIKE ? COLLATE NOCASE LIMIT 5",
            [f"%{politician_name}%"],
        ).fetchall()
        if not rows:
            log.warning("No politician found for: %s", politician_name)
            return []
        return [{"id": r[0], "name": r[1], "slug": _slug(r[1])} for r in rows]

    if all_institutions:
        pols = _select_by_institution(db)
        log.info("Selected %d politicians from ALL target institutions", len(pols))
        return pols

    if notable_only:
        return _select_notable(db)

    # Hybrid: notable politicians first, then top CEAP spenders
    pols: list[dict] = _select_notable(db)
    seen_ids = {p["id"] for p in pols}

    # Fill remaining slots with top CEAP spenders
    remaining = max(0, top_n - len(pols))
    if remaining:
        rows = db.execute(
            """
            SELECT p.id, p.name, SUM(e.value) as total
            FROM politicians p
            JOIN expenses e ON e.deputy_id = p.id
            GROUP BY p.id, p.name
            ORDER BY total DESC
            LIMIT ?
            """,
            [remaining + len(seen_ids)],  # fetch extra to skip dupes
        ).fetchall()

        for r in rows:
            if r[0] not in seen_ids and len(pols) < top_n:
                pols.append({"id": r[0], "name": r[1], "slug": _slug(r[1])})
                seen_ids.add(r[0])

    if not pols:
        # Fallback: any politicians with camara_id
        rows = db.execute(
            "SELECT id, name FROM politicians WHERE camara_id IS NOT NULL LIMIT ?",
            [top_n],
        ).fetchall()
        pols = [{"id": r[0], "name": r[1], "slug": _slug(r[1])} for r in rows]

    log.info("Selected %d focus politicians (%d notable + %d CEAP)",
             len(pols),
             min(len(_select_notable(db)), len(pols)),
             max(0, len(pols) - len(_select_notable(db))))
    return pols


def _select_notable(db) -> list[dict]:
    """Find notable politicians in the DB and apply slug overrides."""
    pols: list[dict] = []
    seen_ids: set[str] = set()

    for name_fragment, slug_override in NOTABLE_POLITICIANS:
        # Support regex-like fragments (e.g. "RENAN.*CALHEIROS")
        if "*" in name_fragment:
            # Convert simple wildcard to SQL LIKE
            like_pattern = name_fragment.replace(".*", "%")
            rows = db.execute(
                "SELECT id, name FROM politicians "
                "WHERE name LIKE ? COLLATE NOCASE LIMIT 3",
                [f"%{like_pattern}%"],
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, name FROM politicians "
                "WHERE name LIKE ? COLLATE NOCASE LIMIT 3",
                [f"%{name_fragment}%"],
            ).fetchall()

        for r in rows:
            if r[0] not in seen_ids:
                pols.append({
                    "id": r[0],
                    "name": r[1],
                    "slug": slug_override,
                })
                seen_ids.add(r[0])

    return pols


def _select_by_institution(db) -> list[dict]:
    """Pull ALL politicians from key institutions (deputies, senators,
    STF, STJ, ministers) for comprehensive historical ingest."""
    pols: list[dict] = []
    seen_ids: set[str] = set()

    # Build a slug override lookup from NOTABLE_POLITICIANS
    slug_lookup: list[tuple[str, str]] = [
        (frag.lower(), slug) for frag, slug in NOTABLE_POLITICIANS
    ]

    for inst in ALL_INSTITUTIONS:
        rows = db.execute(
            'SELECT id, name FROM politicians WHERE roles LIKE ? COLLATE NOCASE',
            [f'%"{inst}"%'],
        ).fetchall()
        log.info("  Institution %-35s → %d politicians", inst, len(rows))

        for r in rows:
            if r[0] in seen_ids:
                continue
            seen_ids.add(r[0])

            # Check for slug override from NOTABLE_POLITICIANS
            name_lower = r[1].lower()
            override = None
            for frag, slug_ov in slug_lookup:
                if ".*" in frag:
                    if re.search(frag.replace(".*", ".*"), name_lower):
                        override = slug_ov
                        break
                elif frag in name_lower:
                    override = slug_ov
                    break

            pols.append({
                "id": r[0],
                "name": r[1],
                "slug": override or _slug(r[1]),
            })

    return pols


# ======================================================================
# Source 1: Querido Diário
# ======================================================================

def _search_querido_diario(
    client: httpx.Client,
    query: str,
    published_since: str,
    published_until: str,
    max_results: int = QD_MAX_RESULTS,
) -> list[dict]:
    """
    Full-text search on Querido Diário gazette API.
    Returns list of {url, title, summary, published_at, territory_name}.
    """
    results: list[dict] = []
    offset = 0
    page_size = 100

    while offset < max_results:
        params = {
            "querystring": query,
            "published_since": published_since,
            "published_until": published_until,
            "size": min(page_size, max_results - offset),
            "offset": offset,
        }
        try:
            resp = client.get(f"{QUERIDO_BASE}/gazettes", params=params, timeout=30)
            if resp.status_code == 403:
                log.warning("Querido Diário returned 403 — may need auth or IP whitelisting")
                break
            if resp.status_code != 200:
                log.warning("Querido Diário HTTP %d for query=%s offset=%d",
                            resp.status_code, query, offset)
                break
            data = resp.json()
        except Exception as exc:
            log.warning("Querido Diário error: %s", exc)
            break

        gazettes = data.get("gazettes", [])
        if not gazettes:
            break

        for g in gazettes:
            url = g.get("url") or g.get("txt_url") or ""
            if not url:
                continue
            excerpts = g.get("excerpts", [])
            summary = " ".join(excerpts)[:500] if excerpts else ""
            territory = g.get("territory_name", "")
            state = g.get("state_code", "")
            title = f"Diário Oficial — {territory}/{state} — {g.get('date', '')}"

            results.append({
                "url": url,
                "title": title,
                "summary": summary,
                "published_at": g.get("date", ""),
            })

        total = data.get("total_gazettes", 0)
        offset += len(gazettes)
        if offset >= total:
            break
        time.sleep(DELAY_QD)

    return results


def _search_querido_diario_themed(
    client: httpx.Client,
    query: str,
    theme: str,
    published_since: str,
    published_until: str,
    max_results: int = 100,
) -> list[dict]:
    """Search Querido Diário themed excerpts (licitações, etc.)."""
    results: list[dict] = []
    offset = 0
    page_size = 50

    while offset < max_results:
        params = {
            "querystring": query,
            "published_since": published_since,
            "published_until": published_until,
            "size": min(page_size, max_results - offset),
            "offset": offset,
        }
        try:
            resp = client.get(
                f"{QUERIDO_BASE}/gazettes/by_theme/{theme}",
                params=params,
                timeout=30,
            )
            if resp.status_code in (403, 404):
                break
            if resp.status_code != 200:
                log.warning("QD themed HTTP %d for theme=%s query=%s",
                            resp.status_code, theme, query)
                break
            data = resp.json()
        except Exception as exc:
            log.warning("QD themed error: %s", exc)
            break

        excerpts = data.get("excerpts", [])
        if not excerpts:
            break

        for ex in excerpts:
            url = ex.get("url") or ex.get("txt_url") or ""
            if not url:
                continue
            territory = ex.get("territory_name", "")
            state = ex.get("state_code", "")
            txt_excerpts = ex.get("excerpts", [])
            summary = " ".join(txt_excerpts)[:500] if txt_excerpts else ""
            title = f"[{theme}] Diário Oficial — {territory}/{state} — {ex.get('date', '')}"

            results.append({
                "url": url,
                "title": title,
                "summary": summary,
                "published_at": ex.get("date", ""),
            })

        total = data.get("total_excerpts", 0)
        offset += len(excerpts)
        if offset >= total:
            break
        time.sleep(DELAY_QD)

    return results


def ingest_querido_diario(
    store: HistoryStore,
    politicians: list[dict],
    since: str,
    until: str,
    existing_ids: set[str],
) -> int:
    """Search Querido Diário for gazette mentions of focus politicians."""
    log.info("=" * 60)
    log.info("SOURCE: Querido Diário — %d politicians, %s → %s", len(politicians), since, until)
    log.info("=" * 60)

    total_new = 0

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0"},
        timeout=httpx.Timeout(20, connect=10),
    ) as client:
        # Quick connectivity check
        try:
            ping = client.get(f"{QUERIDO_BASE}/gazettes", params={"size": 1}, timeout=10)
            if ping.status_code == 403:
                log.error("Querido Diário API returned 403 — skipping this source")
                return 0
            log.info("Querido Diário API is reachable (HTTP %d)", ping.status_code)
        except Exception as exc:
            log.error("Cannot reach Querido Diário API: %s — skipping", exc)
            return 0

        pbar = tqdm(
            politicians,
            desc="Querido Diário",
            unit="pol",
            leave=True,
            dynamic_ncols=True,
            file=sys.stderr,
        )
        for pol in pbar:
            pbar.set_postfix({"politician": pol["name"][:28]}, refresh=True)

            # Main gazette search
            results = _search_querido_diario(client, pol["name"], since, until)

            # Also search themed excerpts (licitações e contratos)
            for theme in QD_THEMES:
                themed = _search_querido_diario_themed(
                    client, pol["name"], theme, since, until, max_results=50,
                )
                results.extend(themed)

            new_items: list[NewsItem] = []
            for r in results:
                item_id = _url_hash(r["url"])
                if item_id in existing_ids:
                    continue

                new_items.append(NewsItem(
                    id=item_id,
                    url=r["url"],
                    title=r["title"][:300],
                    summary=r["summary"][:500],
                    published_at=r["published_at"] or None,
                    source="querido_diario",
                    source_url=QUERIDO_BASE,
                    politician_mentions=[pol["id"]],
                ))
                existing_ids.add(item_id)

            if new_items:
                store.upsert_news_items(new_items)
                total_new += len(new_items)
                tqdm.write(f"  ✓ {pol['name'][:35]}: {len(new_items)} gazette items")

            time.sleep(DELAY_QD)

    log.info("Querido Diário total: %d new items", total_new)
    return total_new


# ======================================================================
# Source 2: GDELT DOC 2.0
# ======================================================================

def _search_gdelt(
    client: httpx.Client,
    politician_name: str,
    start_dt: str | None = None,  # YYYYMMDDHHMMSS
    end_dt: str | None = None,
) -> list[dict]:
    """
    Search GDELT DOC 2.0 for news articles mentioning a politician.
    Returns list of {url, title, published_at, domain}.

    NOTE: GDELT only covers a rolling 3-month window.
    """
    query_parts = [
        f'"{politician_name}"',
        "sourcecountry:brazil",
        "sourcelang:portuguese",
    ]
    if start_dt:
        query_parts.append(f"STARTDATETIME:{start_dt}")
    if end_dt:
        query_parts.append(f"ENDDATETIME:{end_dt}")

    params = {
        "query": " ".join(query_parts),
        "mode": "artlist",
        "format": "json",
        "maxrecords": GDELT_MAX_RESULTS,
        "sort": "DateDesc",
    }

    try:
        resp = client.get(GDELT_BASE, params=params, timeout=30)
        if resp.status_code != 200:
            log.warning("GDELT HTTP %d for %s", resp.status_code, politician_name)
            return []
        data = resp.json()
    except httpx.TimeoutException:
        log.warning("GDELT timeout for %s", politician_name)
        return []
    except Exception as exc:
        log.warning("GDELT error for %s: %s", politician_name, exc)
        return []

    articles = data.get("articles", [])
    results = []
    for a in articles:
        url = a.get("url", "")
        if not url:
            continue
        seen_date = a.get("seendate", "")
        # seendate format: "20230815T123456Z"
        pub = ""
        if seen_date:
            try:
                pub = dt.datetime.strptime(
                    seen_date.replace("Z", ""), "%Y%m%dT%H%M%S"
                ).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pub = seen_date

        results.append({
            "url": url,
            "title": a.get("title", ""),
            "published_at": pub,
            "domain": a.get("domain", ""),
        })

    return results


def ingest_gdelt(
    store: HistoryStore,
    politicians: list[dict],
    existing_ids: set[str],
) -> int:
    """Search GDELT DOC 2.0 for recent news about focus politicians."""
    log.info("=" * 60)
    log.info("SOURCE: GDELT DOC 2.0 — %d politicians (last 3 months)", len(politicians))
    log.info("=" * 60)

    total_new = 0

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0"},
        timeout=httpx.Timeout(10, connect=8),
    ) as client:
        # Quick connectivity check
        try:
            _search_gdelt(client, "teste", start_dt=None, end_dt=None)
            log.info("GDELT API is reachable")
        except Exception as exc:
            log.error("Cannot reach GDELT API: %s — skipping", exc)
            return 0

        pbar = tqdm(
            politicians,
            desc="GDELT",
            unit="pol",
            leave=True,
            dynamic_ncols=True,
            file=sys.stderr,
        )
        for pol in pbar:
            pbar.set_postfix({"politician": pol["name"][:28]}, refresh=True)

            articles = _search_gdelt(client, pol["name"])

            new_items: list[NewsItem] = []
            for a in articles:
                item_id = _url_hash(a["url"])
                if item_id in existing_ids:
                    continue

                new_items.append(NewsItem(
                    id=item_id,
                    url=a["url"],
                    title=a["title"][:300],
                    summary="",  # GDELT artlist doesn't return summaries
                    published_at=a["published_at"] or None,
                    source="gdelt",
                    source_url=a.get("domain", ""),
                    politician_mentions=[pol["id"]],
                ))
                existing_ids.add(item_id)

            if new_items:
                store.upsert_news_items(new_items)
                total_new += len(new_items)
                tqdm.write(f"  ✓ {pol['name'][:35]}: {len(new_items)} GDELT articles")

            time.sleep(DELAY_GDELT)

    log.info("GDELT total: %d new items", total_new)
    return total_new


# ======================================================================
# Source 3: Wayback CDX
# ======================================================================

def _search_wayback_cdx(
    client: httpx.Client,
    domain_prefix: str,
    slug_regex: str,
    from_year: int,
    to_year: int,
    limit: int = WAYBACK_MAX_PER_DOM,
) -> list[dict]:
    """
    Query the Wayback CDX API for archived URLs matching a politician slug.

    Uses regex filter on the 'original' URL field to find articles whose
    URL path contains the politician's name-slug.

    Returns list of {url, timestamp, wayback_url}.
    """
    # Build the CDX URL manually — httpx's param encoding breaks CDX regex
    # filters and URL wildcards (CDX needs literal *, :, / — not %2A, %3A, %2F)
    filter_parts = "&".join([
        f"filter=original:.*{slug_regex}.*",
        "filter=statuscode:200",
        "filter=mimetype:text/html",
    ])
    raw_url = (
        f"{CDX_BASE}?url={domain_prefix}*&matchType=prefix&output=json"
        f"&fl=timestamp,original,statuscode,mimetype"
        f"&{filter_parts}"
        f"&collapse=urlkey&from={from_year}&to={to_year + 1}&limit={limit}"
    )

    try:
        resp = client.get(raw_url, timeout=60)
        if resp.status_code == 403:
            log.debug("Wayback CDX 403 for %s", domain_prefix)
            return []
        if resp.status_code != 200:
            log.debug("Wayback CDX HTTP %d for %s + %s",
                      resp.status_code, domain_prefix, slug_regex)
            return []

        # Sometimes CDX returns plain text instead of JSON on errors
        text = resp.text.strip()
        if not text or not text.startswith("["):
            return []

        data = resp.json()
    except httpx.TimeoutException:
        log.debug("Wayback CDX timeout for %s", domain_prefix)
        return []
    except Exception as exc:
        log.debug("Wayback CDX error: %s", exc)
        return []

    if not data or len(data) < 2:
        return []

    # First row is the header: ["timestamp","original","statuscode","mimetype"]
    header = data[0]
    results = []
    for row in data[1:]:
        if len(row) < 2:
            continue
        timestamp = row[0]
        original_url = row[1]

        # Build the Wayback Machine replay URL
        wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"

        # Parse date from timestamp (YYYYMMDDHHMMSS)
        pub = ""
        try:
            pub = dt.datetime.strptime(timestamp[:8], "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            pass

        results.append({
            "url": original_url,
            "wayback_url": wayback_url,
            "timestamp": timestamp,
            "published_at": pub,
        })

    return results


def _extract_title_from_url(url: str) -> str:
    """
    Best-effort title extraction from a Brazilian news URL slug.
    e.g. 'https://...folha.../poder/2023/08/lula-sanciona-marco-temporal.shtml'
    →    'lula sanciona marco temporal'
    """
    path = urllib.parse.urlparse(url).path
    # Get the last path segment (the article slug)
    segments = [s for s in path.split("/") if s]
    if not segments:
        return url
    slug = segments[-1]
    # Remove file extension
    slug = re.sub(r"\.(s?html?|ghtml|php|asp)$", "", slug, flags=re.I)
    # Replace hyphens/underscores with spaces
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title[:200] if title else url[:200]


def ingest_wayback(
    store: HistoryStore,
    politicians: list[dict],
    from_year: int,
    to_year: int,
    existing_ids: set[str],
) -> int:
    """
    Search Wayback CDX for archived news articles mentioning focus politicians.

    Strategy: for each politician, build a regex from their name-slug and
    search each major news domain's politics section for matching URLs.
    """
    log.info("=" * 60)
    log.info("SOURCE: Wayback CDX — %d politicians, %d→%d across %d domains",
             len(politicians), from_year, to_year, len(WAYBACK_DOMAINS))
    log.info("=" * 60)

    total_new = 0

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0 (academic research)"},
        timeout=httpx.Timeout(45, connect=10),
    ) as client:
        pbar = tqdm(
            politicians,
            desc="Wayback CDX",
            unit="pol",
            leave=True,
            dynamic_ncols=True,
            file=sys.stderr,
        )
        for pol in pbar:
            slug = pol["slug"]
            pbar.set_postfix({"politician": pol["name"][:28]}, refresh=True)
            # Skip very short slugs that would match too broadly
            if len(slug) < 3:
                tqdm.write(f"  skip {pol['name']} (slug too short: '{slug}')")
                continue

            # If the slug was set by NOTABLE_POLITICIANS, use it directly
            # (these are already optimized single-word slugs like "lula").
            # Otherwise build a CDX-compatible regex from multi-part slugs.
            slug_parts = slug.split("-")
            if len(slug_parts) <= 2:
                # Short slug (notable override or simple name) — use as-is
                slug_regex = re.escape(slug)
            elif len(slug_parts) > 3:
                distinctive = [p for p in slug_parts if len(p) > 2]
                if len(distinctive) >= 2:
                    slug_regex = ".+".join(re.escape(p) for p in distinctive[-2:])
                else:
                    slug_regex = re.escape(slug)
            else:
                slug_regex = re.escape(slug)

            pol_new = 0
            for domain_prefix, domain_label in WAYBACK_DOMAINS:
                results = _search_wayback_cdx(
                    client, domain_prefix, slug_regex, from_year, to_year,
                )

                new_items: list[NewsItem] = []
                for r in results:
                    item_id = _url_hash(r["url"])
                    if item_id in existing_ids:
                        continue

                    title = _extract_title_from_url(r["url"])

                    new_items.append(NewsItem(
                        id=item_id,
                        url=r["wayback_url"],
                        title=f"[{domain_label}] {title}",
                        summary=f"Archived article from {domain_label}. Original: {r['url']}",
                        published_at=r["published_at"] or None,
                        source="wayback",
                        source_url=domain_prefix,
                        politician_mentions=[pol["id"]],
                    ))
                    existing_ids.add(item_id)

                if new_items:
                    store.upsert_news_items(new_items)
                    pol_new += len(new_items)

                time.sleep(DELAY_WAYBACK)

            if pol_new:
                tqdm.write(f"  ✓ {pol['name'][:35]}: {pol_new} archived articles")
            total_new += pol_new
            pbar.set_postfix({"politician": pol["name"][:28], "found": total_new}, refresh=True)

    log.info("Wayback CDX total: %d new items", total_new)
    return total_new


def ingest_wayback_keywords(
    store: HistoryStore,
    politicians: list[dict],
    from_year: int,
    to_year: int,
    existing_ids: set[str],
) -> int:
    """
    Search Wayback CDX for corruption-related articles by keyword in URL.

    Instead of searching per-politician, this searches for corruption-related
    terms in article URLs (e.g. 'corrupcao', 'lava-jato', 'operacao-').
    Then does entity-linking against politicians in the DB.

    The ``politicians`` arg is only used for entity-linking; the CDX search
    is keyword-driven.
    """
    log.info("=" * 60)
    log.info("SOURCE: Wayback CDX Keywords — %d terms, %d→%d across %d domains",
             len(CORRUPTION_KEYWORDS), from_year, to_year, len(WAYBACK_DOMAINS))
    log.info("=" * 60)

    # Build a name index for entity-linking (normalized surname → pol id)
    name_index: dict[str, list[str]] = {}
    for pol in politicians:
        name = _normalize(pol["name"])
        parts = name.split()
        # Index full name
        name_index.setdefault(name, []).append(pol["id"])
        # Index last 2 words (>3 chars each)
        significant = [p for p in parts if len(p) > 3]
        if len(significant) >= 2:
            for word in significant[-2:]:
                name_index.setdefault(word, []).append(pol["id"])
        elif significant:
            name_index.setdefault(significant[-1], []).append(pol["id"])
        # Index the slug itself
        slug = pol.get("slug", _slug(pol["name"]))
        name_index.setdefault(slug.replace("-", " "), []).append(pol["id"])

    total_new = 0

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0 (academic research)"},
        timeout=httpx.Timeout(45, connect=10),
    ) as client:
        pbar = tqdm(
            CORRUPTION_KEYWORDS,
            desc="Wayback Keywords",
            unit="kw",
            leave=True,
            dynamic_ncols=True,
            file=sys.stderr,
        )
        for keyword, label in pbar:
            pbar.set_postfix({"keyword": label[:30]}, refresh=True)
            kw_new = 0

            for domain_prefix, domain_label in WAYBACK_DOMAINS:
                results = _search_wayback_cdx(
                    client, domain_prefix,
                    re.escape(keyword),  # exact keyword match in URL
                    from_year, to_year,
                    limit=200,
                )

                new_items: list[NewsItem] = []
                for r in results:
                    item_id = _url_hash(r["url"])
                    if item_id in existing_ids:
                        continue

                    title = _extract_title_from_url(r["url"])

                    # Entity-link: check if any politician name appears in URL
                    url_lower = _normalize(r["url"].replace("-", " "))
                    mentions = set()
                    for name_key, pol_ids in name_index.items():
                        if len(name_key) > 3 and name_key in url_lower:
                            mentions.update(pol_ids)

                    new_items.append(NewsItem(
                        id=item_id,
                        url=r["wayback_url"],
                        title=f"[{domain_label}] {title}",
                        summary=f"Keyword '{keyword}' ({label}). Archived from {domain_label}. Original: {r['url']}",
                        published_at=r["published_at"] or None,
                        source="wayback-kw",
                        source_url=domain_prefix,
                        politician_mentions=list(mentions) if mentions else [],
                    ))
                    existing_ids.add(item_id)

                if new_items:
                    store.upsert_news_items(new_items)
                    kw_new += len(new_items)

                time.sleep(DELAY_WAYBACK)

            if kw_new:
                tqdm.write(f"  ✓ '{keyword}' ({label}): {kw_new} articles")
            total_new += kw_new

    log.info("Wayback CDX Keywords total: %d new items", total_new)
    return total_new


# ======================================================================
# Orchestrator
# ======================================================================

SOURCES = {
    "querido": ingest_querido_diario,
    "gdelt": ingest_gdelt,
    "wayback": ingest_wayback,
}


def run_all(
    store: HistoryStore,
    politicians: list[dict],
    from_year: int = 2010,
    to_year: int | None = None,
    sources: list[str] | None = None,
    keywords: bool = False,
) -> dict[str, int]:
    """Run selected sources and return {source_name: count_new}."""
    if to_year is None:
        to_year = dt.date.today().year

    since_str = f"{from_year}-01-01"
    until_str = f"{to_year}-12-31"

    # Preload existing IDs to avoid duplicates across sources
    try:
        existing_ids = {
            r[0] for r in store._db.execute("SELECT id FROM news_items").fetchall()
        }
    except Exception:
        existing_ids = set()
    log.info("Existing news items in DB: %d", len(existing_ids))

    results: dict[str, int] = {}
    active_sources = sources or ["querido", "gdelt", "wayback"]

    for src in active_sources:
        if src == "querido":
            n = ingest_querido_diario(store, politicians, since_str, until_str, existing_ids)
        elif src == "gdelt":
            n = ingest_gdelt(store, politicians, existing_ids)
        elif src == "wayback":
            n = ingest_wayback(store, politicians, from_year, to_year, existing_ids)
        else:
            log.warning("Unknown source: %s", src)
            continue
        results[src] = n

    # Run corruption keyword search if requested
    if keywords:
        n = ingest_wayback_keywords(store, politicians, from_year, to_year, existing_ids)
        results["wayback-kw"] = n

    return results


# ======================================================================
# Report
# ======================================================================

def print_report(store: HistoryStore) -> None:
    """Print summary of historical news data in the DB."""
    db = store._db
    total = store.count_news_items()

    print(f"\n{'='*65}")
    print(f"  HISTORICAL NEWS — {total:,} items in DB")
    print(f"{'='*65}")

    # By source
    rows = db.execute(
        "SELECT source, COUNT(*) as n FROM news_items GROUP BY source ORDER BY n DESC"
    ).fetchall()
    if rows:
        print("\n  By source:")
        for source, count in rows:
            print(f"    {source:<25} {count:>7,}")

    # By year
    rows = db.execute(
        "SELECT SUBSTR(published_at, 1, 4) as yr, COUNT(*) "
        "FROM news_items WHERE published_at IS NOT NULL "
        "GROUP BY yr ORDER BY yr"
    ).fetchall()
    if rows:
        print("\n  By year:")
        for year, count in rows:
            if year:
                print(f"    {year}  {count:>7,}")

    # Politicians with most mentions
    rows = db.execute(
        "SELECT pm.value, p.name, COUNT(*) as mentions "
        "FROM news_items ni, json_each(ni.politician_mentions) pm "
        "JOIN politicians p ON p.id = pm.value "
        "GROUP BY pm.value, p.name "
        "ORDER BY mentions DESC LIMIT 15"
    ).fetchall()
    if rows:
        print("\n  Most-mentioned politicians (top 15):")
        for _pid, name, count in rows:
            print(f"    {name:<40} {count:>6,} mentions")

    # Source × year matrix (top sources)
    rows = db.execute(
        "SELECT source, SUBSTR(published_at,1,4) as yr, COUNT(*) "
        "FROM news_items WHERE published_at IS NOT NULL "
        "GROUP BY source, yr ORDER BY source, yr"
    ).fetchall()
    if rows:
        print("\n  Source × Year breakdown:")
        current_src = None
        for src, yr, cnt in rows:
            if src != current_src:
                current_src = src
                print(f"\n    {src}:")
            if yr:
                print(f"      {yr}: {cnt:,}")

    # Recent items sample
    items = store.recent_news(limit=5)
    if items:
        print(f"\n  Latest 5 items:")
        for item in items:
            print(f"    [{item['published_at'] or 'n/d'}] [{item['source']}]")
            print(f"      {item['title'][:80]}")
            print(f"      {item['url'][:100]}")

    print()


# ======================================================================
# CLI
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Historical news archive ingestion (Querido Diário + GDELT + Wayback)",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        choices=["querido", "gdelt", "wayback"],
        help="Run only a specific source (default: all)",
    )
    parser.add_argument(
        "--politician", type=str, default=None,
        help="Search for a specific politician name",
    )
    parser.add_argument(
        "--top", type=int, default=100,
        help="Number of top politicians by CEAP spending (default: 100)",
    )
    parser.add_argument(
        "--notable", action="store_true",
        help="Only search for well-known/investigated politicians (faster, higher yield)",
    )
    parser.add_argument(
        "--all", action="store_true", dest="all_institutions",
        help="Search ALL deputies, senators, STF, STJ & ministers from DB (~1300 politicians)",
    )
    parser.add_argument(
        "--keywords", action="store_true",
        help="Also run corruption-keyword search across news domains",
    )
    parser.add_argument(
        "--from-year", type=int, default=2010,
        help="Start year (default: 2010)",
    )
    parser.add_argument(
        "--to-year", type=int, default=None,
        help="End year (default: current year)",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print stats report (no fetching)",
    )
    args = parser.parse_args()

    store = HistoryStore()

    if args.report:
        print_report(store)
        return

    # Select politicians
    politicians = select_focus_politicians(
        store, args.politician, args.top,
        notable_only=args.notable,
        all_institutions=args.all_institutions,
    )
    if not politicians:
        log.error("No politicians selected — nothing to do.")
        return

    sources = [args.source] if args.source else None

    log.info("Starting historical ingestion: %d politicians, sources=%s, keywords=%s",
             len(politicians), sources or "all", args.keywords)
    t0 = time.monotonic()

    results = run_all(
        store,
        politicians,
        from_year=args.from_year,
        to_year=args.to_year,
        sources=sources,
        keywords=args.keywords,
    )

    elapsed = time.monotonic() - t0
    log.info("=" * 60)
    log.info("DONE in %.1f min", elapsed / 60)
    for src, count in results.items():
        log.info("  %s: %d new items", src, count)
    log.info("Total news items in DB: %d", store.count_news_items())
    log.info("=" * 60)

    print_report(store)


if __name__ == "__main__":
    main()
