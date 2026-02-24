"""
Tests for src/sources/wikipedia.py — WikipediaClient.
All HTTP requests are mocked; no live network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.sources.wikipedia import WikipediaClient, WikipediaError, WikiSearchResult, WikiSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_response(items: list[dict]) -> dict:
    return {"query": {"search": items}}


def _summary_response(title: str, extract: str, page_id: int = 1, image_url: str | None = None) -> dict:
    resp: dict = {
        "title": title,
        "extract": extract,
        "pageid": page_id,
        "content_urls": {"desktop": {"page": f"https://pt.wikipedia.org/wiki/{title.replace(' ', '_')}"}},
    }
    if image_url:
        resp["thumbnail"] = {"source": image_url}
    return resp


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_returns_results(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = _search_response([
            {"title": "Alexandre de Moraes", "pageid": 42, "snippet": "<b>Alexandre</b> de Moraes é..."},
            {"title": "Alexandre Frota", "pageid": 43, "snippet": "Ator e político"},
        ])
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            results = client.search("Alexandre", limit=2)

        assert len(results) == 2
        assert results[0].title == "Alexandre de Moraes"
        assert results[0].page_id == 42
        # HTML tags should be stripped from snippet
        assert "<b>" not in results[0].snippet

    def test_returns_empty_on_no_results(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = _search_response([])
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            results = client.search("xyz_nobody_known")

        assert results == []

    def test_raises_on_http_error(self) -> None:
        import httpx

        client = WikipediaClient()
        client._client = MagicMock()
        client._client.get.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(WikipediaError, match="search failed"):
            client.search("Lula")


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    def test_returns_summary(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = _summary_response(
            "Lula", "Luiz Inácio Lula da Silva é o 39º e 43º presidente do Brasil.", page_id=100,
            image_url="https://upload.wikimedia.org/img.jpg"
        )
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.get_summary("Lula")

        assert result is not None
        assert result.title == "Lula"
        assert "presidente" in result.extract
        assert result.image_url == "https://upload.wikimedia.org/img.jpg"
        assert result.page_id == 100

    def test_returns_none_on_404(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        result = client.get_summary("NonExistentPage_XYZ")
        assert result is None

    def test_no_image_returns_none_image_url(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = _summary_response("Test", "Some extract.")
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.get_summary("Test")

        assert result.image_url is None


# ---------------------------------------------------------------------------
# get_intro_text
# ---------------------------------------------------------------------------


class TestGetIntroText:
    def test_returns_text_truncated(self) -> None:
        long_text = "X" * 5000
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "query": {"pages": {"12345": {"extract": long_text}}}
        }
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.get_intro_text("Test", max_chars=1000)

        assert result is not None
        assert len(result) == 1000

    def test_returns_none_if_no_extract(self) -> None:
        client = WikipediaClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"query": {"pages": {"12345": {}}}}
        client._client = MagicMock()
        client._client.get.return_value = mock_resp

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.get_intro_text("Missing Page")

        assert result is None


# ---------------------------------------------------------------------------
# enrich_politician
# ---------------------------------------------------------------------------


class TestEnrichPolitician:
    def test_finds_matching_title(self) -> None:
        client = WikipediaClient()

        search_resp = MagicMock()
        search_resp.raise_for_status.return_value = None
        search_resp.json.return_value = _search_response([
            {"title": "Lula", "pageid": 1, "snippet": ""},
            {"title": "Lula (disambiguation)", "pageid": 2, "snippet": ""},
        ])

        summary_resp = MagicMock()
        summary_resp.status_code = 200
        summary_resp.raise_for_status.return_value = None
        summary_resp.json.return_value = _summary_response("Lula", "Presidente do Brasil.", page_id=1)

        client._client = MagicMock()
        client._client.get.side_effect = [search_resp, summary_resp]

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.enrich_politician("Lula")

        assert result is not None
        assert result.title == "Lula"

    def test_returns_none_when_no_search_results(self) -> None:
        client = WikipediaClient()

        search_resp = MagicMock()
        search_resp.raise_for_status.return_value = None
        search_resp.json.return_value = _search_response([])
        client._client = MagicMock()
        client._client.get.return_value = search_resp

        with patch("src.sources.wikipedia.time.sleep"):
            result = client.enrich_politician("XYZ_Nobody")

        assert result is None
