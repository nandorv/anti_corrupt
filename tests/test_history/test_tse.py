"""
Tests for src/sources/tse.py — TSEClient.
HTTP requests are mocked; no live downloads.
"""

from __future__ import annotations

import csv
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from src.sources.tse import TSEClient, TSEError, ELECTION_YEARS


# ---------------------------------------------------------------------------
# Helpers — build fake ZIP/CSV in memory
# ---------------------------------------------------------------------------


def _make_csv_zip(rows: list[dict], filename: str = "data.csv") -> bytes:
    """Create an in-memory ZIP containing a semicolon-delimited CSV."""
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    csv_bytes = buf.getvalue().encode("latin-1")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr(filename, csv_bytes)
    return zip_buf.getvalue()


def _candidate_row(
    name: str = "CANDIDATO TESTE",
    party: str = "PT",
    uf: str = "SP",
    cargo: str = "DEPUTADO FEDERAL",
    status: str = "ELEITO",
    number: str = "13099",
    cpf: str = "12345678901",
    seq: str = "0100012345",
) -> dict:
    return {
        "NM_CANDIDATO": name,
        "SG_PARTIDO": party,
        "SG_UF": uf,
        "DS_CARGO": cargo,
        "DS_SIT_TOT_TURNO": status,
        "NR_CANDIDATO": number,
        "NR_CPF_CANDIDATO": cpf,
        "SQ_CANDIDATO": seq,
    }


# ---------------------------------------------------------------------------
# list_available_years
# ---------------------------------------------------------------------------


class TestListAvailableYears:
    def test_returns_all_years(self) -> None:
        client = TSEClient()
        years = client.list_available_years()
        assert 2022 in years
        assert 1994 in years
        assert len(years) >= 14


# ---------------------------------------------------------------------------
# TSEError on invalid year
# ---------------------------------------------------------------------------


class TestInvalidYear:
    def test_raises_on_invalid_year(self) -> None:
        client = TSEClient()
        with pytest.raises(TSEError, match="not available"):
            client.fetch_candidates(year=2025)  # not an election year

    def test_raises_on_very_old_year(self) -> None:
        client = TSEClient()
        with pytest.raises(TSEError):
            client.fetch_candidates(year=1990)


# ---------------------------------------------------------------------------
# _iter_csv_rows
# ---------------------------------------------------------------------------


class TestIterCsvRows:
    def test_parses_semicolon_csv(self) -> None:
        rows = [_candidate_row("Alice"), _candidate_row("Bob", party="PL")]
        zip_bytes = _make_csv_zip(rows)
        client = TSEClient()
        parsed = list(client._iter_csv_rows(zip_bytes))
        assert len(parsed) == 2
        assert parsed[0]["NM_CANDIDATO"] == "Alice"

    def test_raises_on_empty_zip(self) -> None:
        empty_zip = io.BytesIO()
        with zipfile.ZipFile(empty_zip, "w"):
            pass
        client = TSEClient()
        with pytest.raises(TSEError, match="No CSV"):
            list(client._iter_csv_rows(empty_zip.getvalue()))


# ---------------------------------------------------------------------------
# fetch_candidates (mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetchCandidates:
    def _client_with_zip(self, rows: list[dict]) -> TSEClient:
        """Create a TSEClient whose _download method returns a fake ZIP."""
        client = TSEClient()
        client._download = MagicMock(return_value=_make_csv_zip(rows))
        return client

    def test_basic_fetch(self) -> None:
        rows = [
            _candidate_row("CANDIDATO A", "PT", status="NÃO ELEITO"),
            _candidate_row("CANDIDATO B", "PL", status="ELEITO"),
        ]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022)
        assert len(results) == 2
        assert results[0].candidate_name == "CANDIDATO A"
        assert results[0].elected is False
        assert results[1].elected is True

    def test_state_filter(self) -> None:
        rows = [
            _candidate_row("PESSOA SP", uf="SP"),
            _candidate_row("PESSOA RJ", uf="RJ"),
        ]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022, state="SP")
        assert len(results) == 1
        assert results[0].state == "SP"

    def test_position_filter(self) -> None:
        rows = [
            _candidate_row("DEP FED", cargo="DEPUTADO FEDERAL"),
            _candidate_row("SENADOR", cargo="SENADOR"),
        ]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022, position="DEPUTADO FEDERAL")
        assert len(results) == 1
        assert results[0].position == "DEPUTADO FEDERAL"

    def test_limit_respected(self) -> None:
        rows = [_candidate_row(f"PESSOA {i}") for i in range(10)]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022, limit=3)
        assert len(results) == 3

    def test_skips_rows_with_missing_name(self) -> None:
        rows = [
            {"NM_CANDIDATO": "", "SG_PARTIDO": "PT", "SG_UF": "SP", "DS_CARGO": "DEPUTADO FEDERAL",
             "DS_SIT_TOT_TURNO": "ELEITO", "NR_CANDIDATO": "1", "NR_CPF_CANDIDATO": "123", "SQ_CANDIDATO": "1"},
            _candidate_row("VALID PERSON"),
        ]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022)
        assert len(results) == 1
        assert results[0].candidate_name == "VALID PERSON"

    def test_elected_flag_various_statuses(self) -> None:
        """Test that 'ELEITO POR MÉDIA' and similar are also detected as elected."""
        rows = [
            _candidate_row("ALPHA", status="ELEITO POR MÉDIA"),
            _candidate_row("BETA", status="NÃO ELEITO"),
            _candidate_row("GAMMA", status="ELEITO"),
        ]
        client = self._client_with_zip(rows)
        results = client.fetch_candidates(2022)
        elected = [r for r in results if r.elected]
        not_elected = [r for r in results if not r.elected]
        assert len(elected) == 2
        assert len(not_elected) == 1

    def test_result_id_stable(self) -> None:
        """Same candidate data across two fetches → same ID."""
        rows = [_candidate_row("STABLE PERSON", party="PT", uf="SP")]
        client = self._client_with_zip(rows)
        r1 = client.fetch_candidates(2022)
        r2 = client.fetch_candidates(2022)
        assert r1[0].id == r2[0].id

    def test_raises_on_download_failure(self) -> None:
        import httpx

        client = TSEClient()
        client._client = MagicMock()
        client._client.get.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(TSEError, match="Download failed"):
            client.fetch_candidates(2022)
