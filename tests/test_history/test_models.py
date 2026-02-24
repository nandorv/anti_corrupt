"""
Tests for src/history/models.py
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.history.models import (
    ElectionResult,
    Expense,
    HistoricalEvent,
    Legislature,
    Politician,
    PoliticianRole,
    Vote,
)


# ---------------------------------------------------------------------------
# Politician
# ---------------------------------------------------------------------------


class TestPolitician:
    def test_auto_id_from_wikidata(self) -> None:
        p = Politician(name="Test Person", wikidata_id="Q99999")
        assert p.id == "wikidata:Q99999"

    def test_auto_id_from_camara(self) -> None:
        p = Politician(name="Test Person", camara_id=12345)
        assert p.id == "camara:12345"

    def test_auto_id_random(self) -> None:
        p = Politician(name="Unknown")
        assert p.id.startswith("pol:")
        assert len(p.id) == 12  # "pol:" + 8 hex chars

    def test_explicit_id_preserved(self) -> None:
        p = Politician(id="my-custom-id", name="Test")
        assert p.id == "my-custom-id"

    def test_wikidata_takes_precedence_over_camara(self) -> None:
        p = Politician(name="Test", wikidata_id="Q1", camara_id=100)
        assert p.id == "wikidata:Q1"

    def test_roles_default_empty(self) -> None:
        p = Politician(name="Test")
        assert p.roles == []

    def test_tags_and_sources_default_empty(self) -> None:
        p = Politician(name="Test")
        assert p.tags == []
        assert p.sources == []

    def test_fetched_at_auto_set(self) -> None:
        p = Politician(name="Test")
        assert isinstance(p.fetched_at, dt.datetime)

    def test_full_construction(self) -> None:
        role = PoliticianRole(
            role="Ministro do STF",
            institution="stf",
            start_date="2017-03-22",
        )
        p = Politician(
            name="Alexandre de Moraes",
            birth_date="1968-12-13",
            birth_place="São Paulo, SP",
            wikidata_id="Q2833489",
            camara_id=None,
            roles=[role],
            tags=["stf", "judiciário"],
            sources=["https://www.wikidata.org/wiki/Q2833489"],
        )
        assert p.id == "wikidata:Q2833489"
        assert len(p.roles) == 1
        assert p.roles[0].institution == "stf"


# ---------------------------------------------------------------------------
# HistoricalEvent
# ---------------------------------------------------------------------------


class TestHistoricalEvent:
    def test_auto_id_from_wikidata(self) -> None:
        e = HistoricalEvent(title="Lava Jato", wikidata_id="Q123")
        assert e.id == "event:wikidata:Q123"

    def test_auto_id_random(self) -> None:
        e = HistoricalEvent(title="Some Event")
        assert e.id.startswith("event:")

    def test_explicit_id_preserved(self) -> None:
        e = HistoricalEvent(id="my-event", title="Test")
        assert e.id == "my-event"

    def test_default_type(self) -> None:
        e = HistoricalEvent(title="Test")
        assert e.type == "event"

    def test_lists_default_empty(self) -> None:
        e = HistoricalEvent(title="Test")
        assert e.actors == []
        assert e.institutions == []
        assert e.tags == []


# ---------------------------------------------------------------------------
# Vote
# ---------------------------------------------------------------------------


class TestVote:
    def test_auto_id_stable(self) -> None:
        v1 = Vote(
            deputy_id="camara:100",
            deputy_name="Dep X",
            proposition_id="camara:prop:999",
            vote="SIM",
            date="2023-05-01",
            session_id="sess1",
        )
        v2 = Vote(
            deputy_id="camara:100",
            deputy_name="Dep X",
            proposition_id="camara:prop:999",
            vote="SIM",
            date="2023-05-01",
            session_id="sess1",
        )
        # Same inputs → same ID (hash-based)
        assert v1.id == v2.id
        assert v1.id.startswith("vote:")

    def test_deputy_id_inferred_from_camara_id(self) -> None:
        v = Vote(
            deputy_camara_id=999,
            deputy_name="Dep Y",
            proposition_id="camara:prop:1",
            vote="NÃO",
            date="2023-01-15",
        )
        assert v.deputy_id == "camara:999"

    def test_different_votes_different_ids(self) -> None:
        kwargs = dict(
            deputy_id="camara:1",
            deputy_name="X",
            vote="SIM",
            date="2023-01-01",
        )
        v1 = Vote(proposition_id="camara:prop:1", **kwargs)
        v2 = Vote(proposition_id="camara:prop:2", **kwargs)
        assert v1.id != v2.id


# ---------------------------------------------------------------------------
# ElectionResult
# ---------------------------------------------------------------------------


class TestElectionResult:
    def test_auto_id_stable(self) -> None:
        r1 = ElectionResult(
            year=2022,
            state="SP",
            position="DEPUTADO FEDERAL",
            candidate_name="João Silva",
            party="PT",
        )
        r2 = ElectionResult(
            year=2022,
            state="SP",
            position="DEPUTADO FEDERAL",
            candidate_name="João Silva",
            party="PT",
        )
        assert r1.id == r2.id
        assert r1.id.startswith("tse:")

    def test_different_candidates_different_ids(self) -> None:
        base = dict(year=2022, state="RJ", position="SENADOR", party="MDB")
        r1 = ElectionResult(candidate_name="Alice", **base)
        r2 = ElectionResult(candidate_name="Bob", **base)
        assert r1.id != r2.id

    def test_defaults(self) -> None:
        r = ElectionResult(year=2018, state="MG", position="GOVERNADOR", candidate_name="X", party="PSDB")
        assert r.votes == 0
        assert r.elected is False
        assert r.round == 1


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------


class TestExpense:
    def test_auto_id_stable(self) -> None:
        e1 = Expense(
            deputy_id="camara:100",
            deputy_name="Dep A",
            year=2023,
            month=3,
            category="PASSAGENS AÉREAS",
            supplier="LATAM",
            value=1500.0,
            document_number="NF001",
        )
        e2 = Expense(
            deputy_id="camara:100",
            deputy_name="Dep A",
            year=2023,
            month=3,
            category="PASSAGENS AÉREAS",
            supplier="LATAM",
            value=1500.0,
            document_number="NF001",
        )
        assert e1.id == e2.id
        assert e1.id.startswith("ceap:")

    def test_deputy_id_inferred(self) -> None:
        e = Expense(
            deputy_camara_id=42,
            deputy_name="X",
            year=2022,
            month=1,
            category="COMBUSTÍVEIS",
            supplier="Posto BR",
            value=200.0,
        )
        assert e.deputy_id == "camara:42"


# ---------------------------------------------------------------------------
# Legislature
# ---------------------------------------------------------------------------


class TestLegislature:
    def test_basic(self) -> None:
        leg = Legislature(id=57, start_date="2023-02-01", description="57ª Legislatura")
        assert leg.id == 57
        assert leg.start_date == "2023-02-01"
        assert leg.end_date is None
