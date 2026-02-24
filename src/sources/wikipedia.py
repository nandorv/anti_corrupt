"""
Wikipedia REST API client for Brazilian political content.

Uses the Portuguese Wikipedia (pt.wikipedia.org).
No API key required — all endpoints are public.

Two APIs are used:
  - MediaWiki Action API  — search, extracts, page info
  - REST API v1           — page summaries (fast, cached)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_WIKI_ACTION = "https://pt.wikipedia.org/w/api.php"
_WIKI_REST = "https://pt.wikipedia.org/api/rest_v1"
_HEADERS = {
    "User-Agent": "AntiCorrupt/1.0 (https://github.com/nandorv/anti_corrupt) Python/httpx",
}
_TIMEOUT = 20.0
_SLEEP = 0.2  # polite delay between requests


class WikipediaError(Exception):
    """Raised when a Wikipedia API request fails."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WikiSummary:
    """Summary (lead section) of a Wikipedia page."""

    title: str
    extract: str
    page_id: int
    url: str
    image_url: Optional[str] = None


@dataclass
class WikiSearchResult:
    """A single result from a Wikipedia search query."""

    title: str
    page_id: int
    snippet: str
    url: str


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class WikipediaClient:
    """
    Client for the Portuguese Wikipedia API.

    Provides search, summary, and full-text extraction.
    All methods include a small sleep to avoid rate-limiting.
    """

    def __init__(self, timeout: float = _TIMEOUT):
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout)

    def search(self, query: str, limit: int = 5) -> list[WikiSearchResult]:
        """Search for Wikipedia pages matching a query string."""
        try:
            resp = self._client.get(
                _WIKI_ACTION,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": limit,
                    "format": "json",
                    "utf8": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("query", {}).get("search", []):
                clean_snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                results.append(
                    WikiSearchResult(
                        title=item["title"],
                        page_id=item["pageid"],
                        snippet=clean_snippet,
                        url=f"https://pt.wikipedia.org/wiki/{item['title'].replace(' ', '_')}",
                    )
                )
            time.sleep(_SLEEP)
            return results
        except httpx.HTTPError as exc:
            raise WikipediaError(f"Wikipedia search failed: {exc}") from exc

    def get_summary(self, title: str) -> Optional[WikiSummary]:
        """
        Get the summary (lead section extract) of a Wikipedia page via REST API.
        Returns None if the page does not exist.
        """
        encoded = title.replace(" ", "_")
        try:
            resp = self._client.get(f"{_WIKI_REST}/page/summary/{encoded}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            image_url = None
            if "thumbnail" in data:
                image_url = data["thumbnail"].get("source")
            time.sleep(_SLEEP)
            return WikiSummary(
                title=data.get("title", title),
                extract=data.get("extract", ""),
                page_id=data.get("pageid", 0),
                url=data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                image_url=image_url,
            )
        except httpx.HTTPError as exc:
            raise WikipediaError(f"Wikipedia summary request failed for '{title}': {exc}") from exc

    def get_intro_text(self, title: str, max_chars: int = 4000) -> Optional[str]:
        """
        Fetch the introduction section of a Wikipedia page as plain text.
        Uses the MediaWiki Action API with exintro + explaintext.
        Returns up to `max_chars` characters.
        """
        try:
            resp = self._client.get(
                _WIKI_ACTION,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "titles": title,
                    "format": "json",
                    "utf8": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "")
                if extract:
                    time.sleep(_SLEEP)
                    return extract[:max_chars]
            return None
        except httpx.HTTPError as exc:
            raise WikipediaError(f"Wikipedia intro request failed for '{title}': {exc}") from exc

    def enrich_politician(self, name: str) -> Optional[WikiSummary]:
        """
        Look up a politician by name and return their Wikipedia summary.

        Strategy:
        1. Search for the name.
        2. Prefer a result whose title contains the search name.
        3. Fall back to the first result.
        """
        results = self.search(name, limit=3)
        if not results:
            return None
        # Prefer title that contains the name (case-insensitive)
        for result in results:
            if name.lower() in result.title.lower():
                return self.get_summary(result.title)
        return self.get_summary(results[0].title)

    def enrich_event(self, title: str) -> Optional[WikiSummary]:
        """Look up an event or topic by title and return its Wikipedia summary."""
        results = self.search(title, limit=3)
        if not results:
            return None
        for result in results:
            if any(word in result.title.lower() for word in title.lower().split()):
                return self.get_summary(result.title)
        return self.get_summary(results[0].title)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "WikipediaClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
