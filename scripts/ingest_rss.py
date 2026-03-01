"""
RSS feed ingestion pipeline.

Polls a curated list of Brazilian political news feeds, deduplicates
by URL hash, entity-links articles to politicians in the DB, and
stores results in the `news_items` table.

Usage:
    python scripts/ingest_rss.py                # fetch all feeds once
    python scripts/ingest_rss.py --daemon       # loop every 6 hours
    python scripts/ingest_rss.py --report       # show recent news stats
    python scripts/ingest_rss.py --politician "Lula"  # news for one politician

Add to cron:
    0 */6 * * * cd /path/to/anti_corrupt && .venv/bin/python scripts/ingest_rss.py >> output/rss_run.log 2>&1
"""

import sys
import time
import argparse
import datetime
import logging
import hashlib
import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.history.store import HistoryStore
from src.history.models import NewsItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

LOOP_INTERVAL_HOURS = 6

RSS_FEEDS = [
    {
        "name": "agencia_brasil",
        "label": "Agência Brasil",
        "url": "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml",
    },
    {
        "name": "g1_politica",
        "label": "G1 Política",
        "url": "https://g1.globo.com/rss/g1/politica/",
    },
    {
        "name": "folha_poder",
        "label": "Folha de S.Paulo — Poder",
        "url": "https://feeds.folha.uol.com.br/poder/rss091.xml",
    },
    {
        "name": "uol_politica",
        "label": "UOL Política",
        "url": "https://rss.uol.com.br/feed/noticias/noticias/politica.xml",
    },
    {
        "name": "estadao_politica",
        "label": "Estadão Política",
        "url": "https://www.estadao.com.br/rss/politica.xml",
    },
    {
        "name": "metropoles",
        "label": "Metrópoles",
        "url": "https://www.metropoles.com/feed/",
    },
    {
        "name": "poder360",
        "label": "Poder360",
        "url": "https://www.poder360.com.br/feed/",
    },
]

# Namespaces commonly found in RSS/Atom feeds
NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}


def _normalize(text: str) -> str:
    """Lowercase + strip accents for fuzzy name matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _text(el, tag: str, ns: str = "") -> str:
    """Safe element text getter."""
    child = el.find(f"{ns}{tag}" if ns else tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(xml_text: str) -> list[dict]:
    """
    Parse RSS or Atom XML into a flat list of article dicts.
    Returns: [{url, title, summary, published_at}, ...]
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("XML parse error: %s", exc)
        return []

    articles = []
    tag = root.tag.lower()

    # Detect Atom
    is_atom = "atom" in tag or root.tag == "{http://www.w3.org/2005/Atom}feed"

    if is_atom:
        ns_atom = "http://www.w3.org/2005/Atom"
        for entry in root.findall(f"{{{ns_atom}}}entry"):
            link_el = entry.find(f"{{{ns_atom}}}link")
            url = (link_el.get("href") or "") if link_el is not None else ""
            title = _text(entry, f"{{{ns_atom}}}title")
            summary = (_text(entry, f"{{{ns_atom}}}summary") or
                       _text(entry, f"{{{ns_atom}}}content"))
            pub = _text(entry, f"{{{ns_atom}}}updated") or _text(entry, f"{{{ns_atom}}}published")
            articles.append({"url": url, "title": title, "summary": summary, "published_at": pub})
    else:
        # RSS 2.0 / RSS 0.91
        channel = root.find("channel") or root
        for item in channel.findall("item"):
            url = (_text(item, "link") or
                   _text(item, f"{{{NS['atom']}}}link"))
            title = _text(item, "title")
            summary = (_text(item, "description") or
                       item.findtext(f"{{{NS['content']}}}encoded", default=""))
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", " ", summary).strip()[:500]
            pub = (_text(item, "pubDate") or
                   _text(item, f"{{{NS['dc']}}}date"))
            articles.append({"url": url, "title": title, "summary": summary, "published_at": pub})

    return [a for a in articles if a["url"] and a["title"]]


def match_politicians(text: str, politician_index: list[tuple[str, str, str]]) -> list[str]:
    """
    Return list of politician IDs whose names appear in `text`.

    politician_index: [(id, name, normalized_name), ...]
    Only matches names >= 5 chars to avoid false positives on short names.
    """
    text_norm = _normalize(text)
    matched = []
    for pol_id, _name, norm_name in politician_index:
        if len(norm_name) >= 5 and norm_name in text_norm:
            matched.append(pol_id)
    return matched


def build_politician_index(store: HistoryStore) -> list[tuple[str, str, str]]:
    """
    Build a fast lookup index: [(id, name, normalized_name), ...]
    Uses full names and also the most-distinctive part (last 2 words).
    """
    rows = store._db.execute(
        "SELECT id, name FROM politicians WHERE name IS NOT NULL"
    ).fetchall()

    index = []
    seen_norms = set()

    for pol_id, name in rows:
        if not name:
            continue
        # Full name
        norm = _normalize(name)
        if norm not in seen_norms:
            index.append((pol_id, name, norm))
            seen_norms.add(norm)

        # Last 2 words (e.g. "Luiz Inácio Lula da Silva" → "lula da silva" is too long,
        # but "lula da silva" keeps it distinctive; we use last 2 tokens for short matches)
        parts = norm.split()
        if len(parts) >= 2:
            short = " ".join(parts[-2:])
            if len(short) >= 8 and short not in seen_norms:
                index.append((pol_id, name, short))
                seen_norms.add(short)

    logger.info("Built politician index with %d entries (%d politicians)", len(index), len(rows))
    return index


def fetch_feed(feed: dict, client: httpx.Client) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns list of article dicts."""
    try:
        resp = client.get(feed["url"], timeout=20, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning("[%s] HTTP %d", feed["name"], resp.status_code)
            return []
        return parse_feed(resp.text)
    except Exception as exc:
        logger.warning("[%s] fetch error: %s", feed["name"], exc)
        return []


def run_once(store: HistoryStore) -> int:
    """Fetch all feeds, entity-link, and save. Returns count of new items saved."""
    pol_index = build_politician_index(store)

    # Load existing URLs to avoid re-processing
    existing_ids = {r[0] for r in store._db.execute("SELECT id FROM news_items").fetchall()}

    total_new = 0

    with httpx.Client(
        headers={"User-Agent": "anti-corrupt-research/1.0"},
        timeout=20,
    ) as client:
        for feed in RSS_FEEDS:
            logger.info("Fetching %s (%s)...", feed["label"], feed["url"])
            articles = fetch_feed(feed, client)
            logger.info("  → %d articles retrieved", len(articles))

            new_items: list[NewsItem] = []
            for a in articles:
                item_id = "news:" + hashlib.sha1(a["url"].encode()).hexdigest()[:12]
                if item_id in existing_ids:
                    continue

                combined_text = f"{a['title']} {a['summary']}"
                mentions = match_politicians(combined_text, pol_index)

                new_items.append(NewsItem(
                    id=item_id,
                    url=a["url"],
                    title=a["title"],
                    summary=a["summary"][:500],
                    published_at=a["published_at"] or None,
                    source=feed["name"],
                    source_url=feed["url"],
                    politician_mentions=mentions,
                ))
                existing_ids.add(item_id)

            if new_items:
                store.upsert_news_items(new_items)
                with_mentions = sum(1 for n in new_items if n.politician_mentions)
                logger.info("  ✓ %d new items saved (%d with politician mentions)",
                            len(new_items), with_mentions)
                total_new += len(new_items)
            else:
                logger.info("  (no new items)")

            time.sleep(1)  # polite delay between feeds

    return total_new


def print_report(store: HistoryStore, politician_name: str | None = None) -> None:
    """Print recent news stats."""
    if politician_name:
        pols = store.search_politicians(politician_name, limit=5)
        if not pols:
            print(f"No politician found for: {politician_name}")
            return
        pol = pols[0]
        items = store.recent_news(limit=20, politician_id=pol.id)
        print(f"\n📰 Recent news mentioning {pol.name} ({pol.id}):")
        for item in items:
            print(f"  [{item['published_at'] or 'n/d'}] {item['title'][:80]}")
            print(f"    {item['url']}")
        return

    total = store.count_news_items()
    print(f"\n{'='*60}")
    print(f"NEWS ITEMS IN DB: {total:,}")
    print(f"{'='*60}")

    # Breakdown by source
    rows = store._db.execute(
        "SELECT source, COUNT(*) as n FROM news_items GROUP BY source ORDER BY n DESC"
    ).fetchall()
    print("\nBy source:")
    for source, count in rows:
        print(f"  {source:<25} {count:>6,}")

    # Most-mentioned politicians
    print("\nMost mentioned politicians (top 10):")
    rows = store._db.execute(
        "SELECT pm.pol_id, p.name, COUNT(*) as mentions "
        "FROM ("
        "  SELECT json_each.value as pol_id "
        "  FROM news_items, json_each(politician_mentions) "
        ") pm "
        "JOIN politicians p ON p.id = pm.pol_id "
        "GROUP BY pm.pol_id, p.name "
        "ORDER BY mentions DESC LIMIT 10"
    ).fetchall()
    for pol_id, name, count in rows:
        print(f"  {name:<35} {count:>5} mentions")

    # Recent items
    print("\nLast 10 items:")
    for item in store.recent_news(limit=10):
        print(f"  [{item['published_at'] or 'n/d'}] [{item['source']}] {item['title'][:70]}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="RSS feed ingestion pipeline")
    parser.add_argument("--daemon", action="store_true",
                        help=f"Loop every {LOOP_INTERVAL_HOURS}h indefinitely")
    parser.add_argument("--report", action="store_true",
                        help="Print news stats, no fetching")
    parser.add_argument("--politician", type=str, default=None,
                        help="Show recent news for a specific politician")
    args = parser.parse_args()

    store = HistoryStore()

    if args.report or args.politician:
        print_report(store, politician_name=args.politician)
        return

    if args.daemon:
        logger.info("Starting daemon mode — polling every %dh", LOOP_INTERVAL_HOURS)
        while True:
            start = time.monotonic()
            try:
                n = run_once(store)
                logger.info("Cycle complete: %d new items", n)
            except Exception as exc:
                logger.error("Cycle error: %s", exc)
            elapsed = time.monotonic() - start
            sleep_secs = max(0, LOOP_INTERVAL_HOURS * 3600 - elapsed)
            logger.info("Sleeping %.0fh until next cycle...", sleep_secs / 3600)
            time.sleep(sleep_secs)
    else:
        n = run_once(store)
        logger.info("Done: %d new items saved", n)
        print_report(store)


if __name__ == "__main__":
    main()
