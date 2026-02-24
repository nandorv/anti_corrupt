"""Tests for src/sources/rss.py — RSS feed aggregator."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.sources.rss import FEEDS, FeedArticle, RSSFetcher


# ---------------------------------------------------------------------------
# FeedArticle
# ---------------------------------------------------------------------------


class TestFeedArticle:
    """Unit tests for the FeedArticle dataclass."""

    def _make_entry(
        self,
        link: str = "https://example.com/article",
        title: str = "Lula sanciona nova lei",
        summary: str = "Resumo do artigo sobre política.",
        published_parsed: tuple | None = (2024, 3, 15, 10, 0, 0, 0, 0, 0),
        content: list | None = None,
    ) -> MagicMock:
        entry = MagicMock()
        entry.get = lambda key, default="": {
            "link": link,
            "title": title,
            "summary": summary,
        }.get(key, default)
        entry.published_parsed = published_parsed
        entry.summary = summary
        entry.content = content
        return entry

    def _meta(
        self,
        source_name: str = "Test Source",
        language: str = "pt-BR",
        tags: list | None = None,
    ) -> dict:
        return {
            "source_name": source_name,
            "language": language,
            "tags": tags or ["política"],
        }

    def test_from_entry_basic(self):
        entry = self._make_entry()
        article = FeedArticle.from_entry(entry, "test_key", self._meta())

        assert article.url == "https://example.com/article"
        assert article.title == "Lula sanciona nova lei"
        assert article.source_key == "test_key"
        assert article.source_name == "Test Source"
        assert article.language == "pt-BR"
        assert "política" in article.tags

    def test_id_is_sha256_of_url(self):
        entry = self._make_entry(link="https://example.com/unique")
        article = FeedArticle.from_entry(entry, "k", self._meta())
        expected_id = hashlib.sha256(b"https://example.com/unique").hexdigest()[:16]
        assert article.id == expected_id

    def test_published_at_parsed_correctly(self):
        entry = self._make_entry(published_parsed=(2024, 3, 15, 10, 30, 0, 0, 0, 0))
        article = FeedArticle.from_entry(entry, "k", self._meta())
        assert article.published_at is not None
        assert article.published_at.year == 2024
        assert article.published_at.month == 3
        assert article.published_at.day == 15

    def test_published_at_none_when_missing(self):
        entry = self._make_entry(published_parsed=None)
        entry.published_parsed = None
        article = FeedArticle.from_entry(entry, "k", self._meta())
        assert article.published_at is None

    def test_content_field_preferred_over_summary(self):
        entry = self._make_entry(
            content=[{"value": "Full article content here."}]
        )
        article = FeedArticle.from_entry(entry, "k", self._meta())
        assert article.summary == "Full article content here."

    def test_to_dict_keys(self):
        entry = self._make_entry()
        article = FeedArticle.from_entry(entry, "k", self._meta())
        d = article.to_dict()
        required_keys = {"id", "url", "title", "summary", "published_at",
                         "source_key", "source_name", "language", "tags", "full_text"}
        assert required_keys == set(d.keys())

    def test_full_text_default_none(self):
        entry = self._make_entry()
        article = FeedArticle.from_entry(entry, "k", self._meta())
        assert article.full_text is None


# ---------------------------------------------------------------------------
# FEEDS registry
# ---------------------------------------------------------------------------


class TestFeedsRegistry:
    """Tests for the FEEDS constant."""

    def test_has_ten_feeds(self):
        assert len(FEEDS) == 10

    def test_each_feed_has_url(self):
        for key, meta in FEEDS.items():
            assert "url" in meta, f"Feed '{key}' missing 'url'"
            assert meta["url"].startswith("http"), f"Feed '{key}' URL not HTTP"

    def test_each_feed_has_source_name(self):
        for key, meta in FEEDS.items():
            assert "source_name" in meta
            assert len(meta["source_name"]) > 0

    def test_each_feed_has_language(self):
        for key, meta in FEEDS.items():
            assert "language" in meta

    def test_each_feed_has_tags(self):
        for key, meta in FEEDS.items():
            assert "tags" in meta
            assert isinstance(meta["tags"], list)

    def test_known_feeds_present(self):
        assert "agencia_brasil" in FEEDS
        assert "agencia_senado" in FEEDS
        assert "agencia_camara" in FEEDS
        assert "stf_noticias" in FEEDS


# ---------------------------------------------------------------------------
# RSSFetcher (with mocked feedparser)
# ---------------------------------------------------------------------------


class TestRSSFetcher:
    """Tests for RSSFetcher — all network calls mocked."""

    def _mock_feed_dict(self, entries: list[MagicMock]) -> MagicMock:
        """Return a feedparser-like dict mock with .get() and .entries."""
        feed = MagicMock()
        feed.get = lambda k, d=None: entries if k == "entries" else d
        feed.bozo = False
        return feed

    def _make_entry(self, url: str, title: str) -> MagicMock:
        entry = MagicMock()
        entry.get = lambda k, d="": {"link": url, "title": title}.get(k, d)
        entry.published_parsed = (2024, 1, 1, 0, 0, 0, 0, 0, 0)
        entry.summary = "Resumo de notícia."
        entry.content = None
        return entry

    def _mock_httpx_response(self, content: bytes = b"<rss/>") -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.raise_for_status = MagicMock()
        return resp

    @patch("src.sources.rss.feedparser.parse")
    @patch("src.sources.rss.httpx.get")
    def test_fetch_feed_returns_articles(self, mock_httpx_get, mock_parse):
        entries = [
            self._make_entry("https://ex.com/1", "Notícia 1"),
            self._make_entry("https://ex.com/2", "Notícia 2"),
        ]
        mock_httpx_get.return_value = self._mock_httpx_response()
        mock_parse.return_value = self._mock_feed_dict(entries)

        fetcher = RSSFetcher()
        articles = fetcher.fetch_feed("agencia_brasil")

        assert len(articles) == 2
        assert all(isinstance(a, FeedArticle) for a in articles)

    @patch("src.sources.rss.feedparser.parse")
    @patch("src.sources.rss.httpx.get")
    def test_fetch_feed_applies_max_articles(self, mock_httpx_get, mock_parse):
        entries = [
            self._make_entry(f"https://ex.com/{i}", f"Notícia {i}")
            for i in range(25)
        ]
        mock_httpx_get.return_value = self._mock_httpx_response()
        mock_parse.return_value = self._mock_feed_dict(entries)

        fetcher = RSSFetcher(max_articles_per_feed=10)
        articles = fetcher.fetch_feed("agencia_brasil")
        assert len(articles) == 10

    @patch("src.sources.rss.feedparser.parse")
    @patch("src.sources.rss.httpx.get")
    def test_fetch_feed_unknown_key_raises(self, mock_httpx_get, mock_parse):
        fetcher = RSSFetcher()
        with pytest.raises(KeyError):
            fetcher.fetch_feed("nonexistent_feed")

    @patch("src.sources.rss.feedparser.parse")
    @patch("src.sources.rss.httpx.get")
    def test_fetch_feed_empty_entries_returns_empty(self, mock_httpx_get, mock_parse):
        mock_httpx_get.return_value = self._mock_httpx_response()
        mock_parse.return_value = self._mock_feed_dict([])

        fetcher = RSSFetcher()
        articles = fetcher.fetch_feed("agencia_brasil")
        assert articles == []

    @patch("src.sources.rss.feedparser.parse")
    @patch("src.sources.rss.httpx.get")
    def test_fetch_all_aggregates_all_feeds(self, mock_httpx_get, mock_parse):
        entries = [self._make_entry("https://ex.com/x", "X")]
        mock_httpx_get.return_value = self._mock_httpx_response()
        mock_parse.return_value = self._mock_feed_dict(entries)

        fetcher = RSSFetcher()
        all_articles = fetcher.fetch_all()

        # Should have articles from every pt-BR feed
        assert len(all_articles) > 0
        source_keys = {a.source_key for a in all_articles}
        assert len(source_keys) > 1
