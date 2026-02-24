"""Tests for src/sources/scraper.py — article full-text extractor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.sources.scraper import ArticleScraper, ExtractedArticle


# ---------------------------------------------------------------------------
# ExtractedArticle
# ---------------------------------------------------------------------------


class TestExtractedArticle:
    """Unit tests for the ExtractedArticle dataclass."""

    def _make(
        self,
        url: str = "https://example.com/article",
        text: str = "Some article text " * 10,  # > 80 words
        success: bool = True,
        error: str | None = None,
    ) -> ExtractedArticle:
        return ExtractedArticle(
            url=url,
            title="Test Article",
            text=text,
            html="<html></html>",
            language="pt",
            author="Author",
            date="2024-01-01",
            success=success,
            error=error,
        )

    def test_word_count_with_text(self):
        text = "word " * 100
        article = self._make(text=text)
        assert article.word_count == 100

    def test_word_count_with_none_text(self):
        article = self._make(text=None)
        assert article.word_count == 0

    def test_is_usable_above_threshold(self):
        text = "word " * 90  # 90 words — above 80 threshold
        article = self._make(text=text, success=True)
        assert article.is_usable is True

    def test_is_usable_below_threshold(self):
        text = "word " * 50  # 50 words — below 80
        article = self._make(text=text, success=True)
        assert article.is_usable is False

    def test_is_usable_false_when_not_success(self):
        text = "word " * 200
        article = self._make(text=text, success=False)
        assert article.is_usable is False

    def test_is_usable_false_when_text_none(self):
        article = self._make(text=None, success=True)
        assert article.is_usable is False


# ---------------------------------------------------------------------------
# ArticleScraper
# ---------------------------------------------------------------------------


LONG_ARTICLE_TEXT = """
O Supremo Tribunal Federal (STF) decidiu, por maioria, que as emendas
parlamentares impositivas devem obedecer às mesmas regras de transparência
que as demais transferências do orçamento público. A decisão, proferida
em plenário, tem repercussão direta sobre a gestão dos recursos federais.

A ministra relatora destacou que o princípio da publicidade exige que
cidadãos possam identificar quem são os beneficiários das verbas públicas.
Segundo ela, a opacidade em torno das emendas representa uma ameaça ao
controle social e à fiscalização pelos órgãos competentes.

O julgamento ocorreu em meio a um acalorado debate político no Congresso
sobre o chamado orçamento secreto. A Câmara dos Deputados prometeu votar
uma nova regulamentação nos próximos dias para dar cumprimento à decisão
do tribunal. O governo federal também manifestou apoio à maior transparência.
"""


class TestArticleScraper:
    """Tests for ArticleScraper — network calls fully mocked."""

    def test_scraper_creates_context_manager(self):
        """ArticleScraper should work as a context manager."""
        with ArticleScraper() as scraper:
            assert scraper is not None

    @patch("src.sources.scraper.httpx.Client")
    @patch("src.sources.scraper.trafilatura.extract")
    def test_extract_success(self, mock_extract, mock_client_cls):
        """extract() returns usable ExtractedArticle when text is found."""
        mock_extract.return_value = LONG_ARTICLE_TEXT

        mock_response = MagicMock()
        mock_response.text = "<html><body>article</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        scraper = ArticleScraper()
        result = scraper.extract("https://example.com/article")

        assert isinstance(result, ExtractedArticle)
        assert result.success is True
        assert result.text is not None
        assert "Supremo Tribunal Federal" in result.text
        assert result.url == "https://example.com/article"

    @patch("src.sources.scraper.httpx.Client")
    @patch("src.sources.scraper.trafilatura.extract")
    def test_extract_failure_returns_failed_article(self, mock_extract, mock_client_cls):
        """extract() returns success=False when trafilatura returns None."""
        mock_extract.return_value = None

        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        scraper = ArticleScraper()
        result = scraper.extract("https://example.com/empty")

        assert result.success is False
        assert result.is_usable is False

    @patch("src.sources.scraper.httpx.Client")
    def test_extract_http_error_returns_failed_article(self, mock_client_cls):
        """extract() returns success=False on HTTP error."""
        import httpx

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("timeout", request=MagicMock())
        mock_client_cls.return_value = mock_client

        scraper = ArticleScraper()
        result = scraper.extract("https://example.com/timeout")

        assert result.success is False
        assert result.error is not None

    @patch("src.sources.scraper.httpx.Client")
    @patch("src.sources.scraper.trafilatura.extract")
    def test_extract_batch_returns_list(self, mock_extract, mock_client_cls):
        """extract_batch() returns a list of ExtractedArticle objects."""
        mock_extract.return_value = LONG_ARTICLE_TEXT

        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        urls = [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ]
        scraper = ArticleScraper()
        results = scraper.extract_batch(urls)

        assert len(results) == 3
        assert all(isinstance(r, ExtractedArticle) for r in results)
