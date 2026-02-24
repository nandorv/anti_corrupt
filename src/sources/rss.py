"""RSS feed aggregator for Brazilian political news sources."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed registry — curated Brazilian political / institutional news sources
# ---------------------------------------------------------------------------

FEEDS: dict[str, dict] = {
    # Generalist / politics
    "folha_poder": {
        "url": "https://feeds.folha.uol.com.br/poder/rss091.xml",
        "source_name": "Folha de S.Paulo — Poder",
        "language": "pt-BR",
        "tags": ["política", "governo"],
    },
    "g1_politica": {
        "url": "https://g1.globo.com/rss/g1/politica/",
        "source_name": "G1 — Política",
        "language": "pt-BR",
        "tags": ["política"],
    },
    "estadao_politica": {
        "url": "https://www.estadao.com.br/rss/politica.xml",
        "source_name": "Estadão — Política",
        "language": "pt-BR",
        "tags": ["política", "governo"],
    },
    # Institutional / congress
    "congresso_em_foco": {
        "url": "https://congressoemfoco.uol.com.br/feed/",
        "source_name": "Congresso em Foco",
        "language": "pt-BR",
        "tags": ["congresso", "legislativo"],
    },
    # Official
    "agencia_brasil": {
        "url": "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml",
        "source_name": "Agência Brasil",
        "language": "pt-BR",
        "tags": ["governo", "oficial"],
    },
    "agencia_senado": {
        "url": "https://www12.senado.leg.br/noticias/rss/noticias-do-dia.xml",
        "source_name": "Agência Senado",
        "language": "pt-BR",
        "tags": ["senado", "legislativo"],
    },
    "agencia_camara": {
        "url": "https://www.camara.leg.br/noticias/rss",
        "source_name": "Agência Câmara",
        "language": "pt-BR",
        "tags": ["câmara", "legislativo"],
    },
    # Justice / STF
    "stf_noticias": {
        "url": "https://portal.stf.jus.br/noticias/rss.asp",
        "source_name": "STF — Notícias",
        "language": "pt-BR",
        "tags": ["judiciário", "stf"],
    },
    "jota": {
        "url": "https://www.jota.info/feed",
        "source_name": "JOTA",
        "language": "pt-BR",
        "tags": ["judiciário", "direito"],
    },
    # Anti-corruption / transparency
    "transparencia_internacional": {
        "url": "https://www.transparency.org/en/news/rss",
        "source_name": "Transparência Internacional",
        "language": "en",
        "tags": ["corrupção", "transparência"],
    },
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FeedArticle:
    """A single article fetched from an RSS feed."""

    id: str  # sha256 of url
    url: str
    title: str
    summary: str
    published_at: Optional[datetime]
    source_key: str
    source_name: str
    language: str
    tags: list[str] = field(default_factory=list)
    full_text: Optional[str] = None  # populated by scraper later

    @classmethod
    def from_entry(
        cls,
        entry: feedparser.FeedParserDict,
        source_key: str,
        source_meta: dict,
    ) -> "FeedArticle":
        url = entry.get("link", "")
        article_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        # Parse date
        published_at: Optional[datetime] = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        # Summary — prefer content > summary > title
        summary = ""
        if hasattr(entry, "content") and entry.content:
            summary = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            summary = entry.summary or ""

        return cls(
            id=article_id,
            url=url,
            title=entry.get("title", "").strip(),
            summary=summary.strip(),
            published_at=published_at,
            source_key=source_key,
            source_name=source_meta["source_name"],
            language=source_meta["language"],
            tags=list(source_meta.get("tags", [])),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source_key": self.source_key,
            "source_name": self.source_name,
            "language": self.language,
            "tags": self.tags,
            "full_text": self.full_text,
        }


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class RSSFetcher:
    """Fetch and parse one or more RSS feeds."""

    def __init__(
        self,
        feeds: dict[str, dict] | None = None,
        timeout: int = 15,
        max_articles_per_feed: int = 20,
    ) -> None:
        self.feeds = feeds or FEEDS
        self.timeout = timeout
        self.max_articles_per_feed = max_articles_per_feed

    def fetch_feed(self, source_key: str) -> list[FeedArticle]:
        """Fetch a single feed by its registry key."""
        if source_key not in self.feeds:
            raise KeyError(f"Unknown feed key: {source_key!r}")
        meta = self.feeds[source_key]
        return self._parse_feed(source_key, meta)

    def fetch_all(
        self,
        source_keys: list[str] | None = None,
        language_filter: str | None = None,
    ) -> list[FeedArticle]:
        """Fetch all (or specified) feeds; optionally filter by language."""
        keys = source_keys or list(self.feeds.keys())
        articles: list[FeedArticle] = []
        for key in keys:
            meta = self.feeds.get(key)
            if not meta:
                logger.warning("Feed key not found: %s", key)
                continue
            if language_filter and meta.get("language") != language_filter:
                continue
            try:
                batch = self._parse_feed(key, meta)
                articles.extend(batch)
                logger.info("✓ %s — %d articles", key, len(batch))
            except Exception as exc:
                logger.warning("✗ Failed to fetch %s: %s", key, exc)
        return articles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_feed(self, source_key: str, meta: dict) -> list[FeedArticle]:
        url = meta["url"]
        try:
            # Use httpx to fetch raw bytes (better redirect/timeout handling)
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
        except httpx.HTTPError as exc:
            # Fallback: let feedparser try directly
            logger.debug("httpx failed for %s, falling back to feedparser: %s", source_key, exc)
            parsed = feedparser.parse(url)

        entries = parsed.get("entries", [])[: self.max_articles_per_feed]
        articles = []
        for entry in entries:
            try:
                article = FeedArticle.from_entry(entry, source_key, meta)
                if article.url and article.title:
                    articles.append(article)
            except Exception as exc:
                logger.debug("Could not parse entry from %s: %s", source_key, exc)
        return articles


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def scan_news(
    source_keys: list[str] | None = None,
    language_filter: str | None = "pt-BR",
    max_per_feed: int = 20,
) -> list[FeedArticle]:
    """High-level: fetch all Brazilian news feeds, return articles list."""
    fetcher = RSSFetcher(max_articles_per_feed=max_per_feed)
    return fetcher.fetch_all(source_keys=source_keys, language_filter=language_filter)
