"""Article full-text extractor using trafilatura."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
import trafilatura
from trafilatura.settings import use_config

logger = logging.getLogger(__name__)

# Trafilatura config: aggressive extraction, fallback to readability
_TRAF_CONFIG = use_config()
_TRAF_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "20")


@dataclass
class ExtractedArticle:
    """Full-text extraction result for a URL."""

    url: str
    title: Optional[str]
    text: Optional[str]  # plain text body
    html: Optional[str]  # raw HTML (for debugging)
    language: Optional[str]
    author: Optional[str]
    date: Optional[str]
    success: bool
    error: Optional[str] = None

    @property
    def word_count(self) -> int:
        return len(self.text.split()) if self.text else 0

    @property
    def is_usable(self) -> bool:
        """Minimum quality gate: at least 80 words extracted."""
        return self.success and self.word_count >= 80


class ArticleScraper:
    """Extract full article text from a URL using trafilatura + httpx."""

    def __init__(self, timeout: int = 20, min_words: int = 80) -> None:
        self.timeout = timeout
        self.min_words = min_words
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AntiCorruptBot/1.0; "
                    "+https://github.com/anticorrupt)"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )

    def extract(self, url: str) -> ExtractedArticle:
        """Download and extract the full text from *url*."""
        html: Optional[str] = None
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPError as exc:
            return ExtractedArticle(
                url=url,
                title=None,
                text=None,
                html=None,
                language=None,
                author=None,
                date=None,
                success=False,
                error=f"HTTP error: {exc}",
            )

        # trafilatura extraction
        result = trafilatura.extract(
            html,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            config=_TRAF_CONFIG,
        )

        # Metadata
        meta = trafilatura.extract_metadata(html, default_url=url)
        title = meta.title if meta else None
        author = (
            (meta.author[0] if isinstance(meta.author, list) else meta.author)
            if meta
            else None
        )
        date = meta.date if meta else None
        language = meta.language if meta else None

        if not result:
            return ExtractedArticle(
                url=url,
                title=title,
                text=None,
                html=html,
                language=language,
                author=author,
                date=date,
                success=False,
                error="trafilatura returned no content",
            )

        return ExtractedArticle(
            url=url,
            title=title,
            text=result.strip(),
            html=html,
            language=language,
            author=author,
            date=date,
            success=True,
        )

    def extract_batch(
        self, urls: list[str], stop_on_error: bool = False
    ) -> list[ExtractedArticle]:
        """Extract multiple URLs sequentially. Errors are logged but not raised."""
        results = []
        for url in urls:
            try:
                article = self.extract(url)
                results.append(article)
                status = "✓" if article.is_usable else "~"
                logger.info("%s %s (%d words)", status, url[:80], article.word_count)
            except Exception as exc:
                logger.warning("Unexpected error extracting %s: %s", url, exc)
                if stop_on_error:
                    raise
                results.append(
                    ExtractedArticle(
                        url=url,
                        title=None,
                        text=None,
                        html=None,
                        language=None,
                        author=None,
                        date=None,
                        success=False,
                        error=str(exc),
                    )
                )
        return results

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ArticleScraper":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def extract_article(url: str, timeout: int = 20) -> ExtractedArticle:
    """Single-shot extraction helper."""
    with ArticleScraper(timeout=timeout) as scraper:
        return scraper.extract(url)
