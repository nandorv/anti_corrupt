"""
Tests for src/sources/wikidata.py — WikidataClient.
All HTTP requests are mocked; no live network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.sources.wikidata import WikidataClient, WikidataError


# ---------------------------------------------------------------------------
# Helpers — fake SPARQL responses
# ---------------------------------------------------------------------------

def _binding(person_uri: str, label: str, **extra) -> dict:
    """Build a minimal Wikidata SPARQL binding dict."""
    b: dict = {
        "person": {"type": "uri", "value": f"http://www.wikidata.org/entity/{person_uri}"},
        "personLabel": {"type": "literal", "value": label},
    }
    for k, v in extra.items():
        b[k] = {"type": "literal", "value": v}
    return b


def _event_binding(event_uri: str, label: str, **extra) -> dict:
    b: dict = {
        "event": {"type": "uri", "value": f"http://www.wikidata.org/entity/{event_uri}"},
        "eventLabel": {"type": "literal", "value": label},
    }
    for k, v in extra.items():
        b[k] = {"type": "literal", "value": v}
    return b


def _sparql_response(bindings: list[dict]) -> dict:
    return {"results": {"bindings": bindings}}


# ---------------------------------------------------------------------------
# WikidataClient._query
# ---------------------------------------------------------------------------


class TestWikidataQuery:
    def test_returns_bindings(self) -> None:
        bindings = [_binding("Q1", "Test Person")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = _sparql_response(bindings)
        mock_resp.raise_for_status.return_value = None

        client = WikidataClient()
        client._client = MagicMock()
        client._client.get.return_value = mock_resp
        result = client._query("SELECT * WHERE { }")

        assert len(result) == 1
        assert result[0]["personLabel"]["value"] == "Test Person"

    def test_raises_wikidata_error_on_http_failure(self) -> None:
        import httpx

        with patch("src.sources.wikidata.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            client = WikidataClient()
            client._client = mock_client

            with pytest.raises(WikidataError, match="SPARQL"):
                client._query("SELECT * WHERE { }")


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_val_extracts_value(self) -> None:
        binding = {"label": {"type": "literal", "value": "hello"}}
        assert WikidataClient._val(binding, "label") == "hello"

    def test_val_missing_key_returns_none(self) -> None:
        assert WikidataClient._val({}, "missing") is None

    def test_wid_extracts_qid(self) -> None:
        assert WikidataClient._wid("http://www.wikidata.org/entity/Q12345") == "Q12345"

    def test_wid_empty_returns_none(self) -> None:
        assert WikidataClient._wid("") is None

    def test_date_trims_to_date(self) -> None:
        assert WikidataClient._date("2017-03-22T00:00:00Z") == "2017-03-22"

    def test_date_none_returns_none(self) -> None:
        assert WikidataClient._date(None) is None

    def test_is_qid_true(self) -> None:
        assert WikidataClient._is_qid("Q12345") is True

    def test_is_qid_false_for_name(self) -> None:
        assert WikidataClient._is_qid("Alexandre de Moraes") is False


# ---------------------------------------------------------------------------
# fetch_stf_ministers
# ---------------------------------------------------------------------------


class TestFetchSTFMinisters:
    def _make_client(self, bindings: list[dict]) -> WikidataClient:
        client = WikidataClient()
        client._query = MagicMock(return_value=bindings)
        return client

    def test_returns_politicians(self) -> None:
        bindings = [
            _binding(
                "Q2833489", "Alexandre de Moraes",
                birthDate="1968-12-13T00:00:00Z",
                birthPlaceLabel="São Paulo",
                startDate="2017-03-22T00:00:00Z",
                description="político e jurista brasileiro",
            )
        ]
        client = self._make_client(bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.fetch_stf_ministers()

        assert len(result) == 1
        assert result[0].name == "Alexandre de Moraes"
        assert result[0].wikidata_id == "Q2833489"
        assert result[0].birth_date == "1968-12-13"
        assert len(result[0].roles) == 1
        assert result[0].roles[0].institution == "stf"

    def test_skips_qid_labels(self) -> None:
        bindings = [_binding("Q99", "Q99")]  # label = QID → skip
        client = self._make_client(bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.fetch_stf_ministers()
        assert result == []

    def test_multiple_terms_same_person(self) -> None:
        """Two bindings for the same person → one politician with two roles."""
        bindings = [
            _binding("Q1", "Person A", startDate="2010-01-01T00:00:00Z"),
            _binding("Q1", "Person A", startDate="2015-06-01T00:00:00Z"),
        ]
        client = self._make_client(bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.fetch_stf_ministers()
        assert len(result) == 1
        assert len(result[0].roles) == 2


# ---------------------------------------------------------------------------
# fetch_political_events
# ---------------------------------------------------------------------------


class TestFetchPoliticalEvents:
    def test_returns_events(self) -> None:
        bindings = [
            _event_binding("Q123456", "Operação Lava Jato",
                           date="2014-03-17T00:00:00Z",
                           description="Maior operação anticorrupção do Brasil")
        ]
        client = WikidataClient()
        client._query = MagicMock(return_value=bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.fetch_political_events()

        assert len(result) == 1
        assert result[0].title == "Operação Lava Jato"
        assert result[0].date == "2014-03-17"
        assert result[0].wikidata_id == "Q123456"

    def test_deduplicates_events(self) -> None:
        """Same event appearing twice in SPARQL results → only one HistoricalEvent."""
        bindings = [
            _event_binding("Q1", "Event A", date="2020-01-01T00:00:00Z"),
            _event_binding("Q1", "Event A", date="2020-01-01T00:00:00Z"),
        ]
        client = WikidataClient()
        client._query = MagicMock(return_value=bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.fetch_political_events()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# search_person
# ---------------------------------------------------------------------------


class TestSearchPerson:
    def test_search_returns_politicians(self) -> None:
        bindings = [
            _binding("Q500", "Lula", birthDate="1945-10-27T00:00:00Z", description="35º presidente do Brasil"),
        ]
        client = WikidataClient()
        client._query = MagicMock(return_value=bindings)
        with patch("src.sources.wikidata.time.sleep"):
            result = client.search_person("Lula")
        assert len(result) == 1
        assert result[0].name == "Lula"
