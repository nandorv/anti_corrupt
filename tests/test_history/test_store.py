"""
Tests for src/history/store.py — HistoryStore CRUD operations.
All tests use an in-memory / tmp_path SQLite database.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

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
from src.history.store import HistoryStore


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "test_history.db")


def _politician(**kwargs) -> Politician:
    defaults = dict(
        name="Fulano de Tal",
        wikidata_id="Q99001",
        birth_date="1960-01-15",
        birth_place="São Paulo, SP",
        tags=["stf"],
        sources=["https://example.com"],
    )
    defaults.update(kwargs)
    return Politician(**defaults)


def _event(**kwargs) -> HistoricalEvent:
    defaults = dict(
        title="Operação Teste",
        date="2014-01-01",
        type="scandal",
        summary="Um evento de teste.",
        tags=["corrupção"],
    )
    defaults.update(kwargs)
    return HistoricalEvent(**defaults)


def _vote(**kwargs) -> Vote:
    defaults = dict(
        deputy_id="camara:100",
        deputy_name="Dep Teste",
        proposition_id="camara:prop:500",
        vote="SIM",
        date="2023-03-15",
        session_id="sess99",
    )
    defaults.update(kwargs)
    return Vote(**defaults)


def _election_result(**kwargs) -> ElectionResult:
    defaults = dict(
        year=2022,
        state="SP",
        position="DEPUTADO FEDERAL",
        candidate_name="Candidato Teste",
        party="PSOL",
        elected=True,
        votes=50000,
    )
    defaults.update(kwargs)
    return ElectionResult(**defaults)


def _expense(**kwargs) -> Expense:
    defaults = dict(
        deputy_id="camara:100",
        deputy_name="Dep Teste",
        year=2023,
        month=5,
        category="PASSAGENS AÉREAS",
        supplier="LATAM",
        value=1200.50,
        document_number="NF-123",
    )
    defaults.update(kwargs)
    return Expense(**defaults)


# ---------------------------------------------------------------------------
# Schema & empty state
# ---------------------------------------------------------------------------


class TestStoreInit:
    def test_tables_created(self, store: HistoryStore) -> None:
        tables = store._db.table_names()
        for expected in ["politicians", "historical_events", "votes", "election_results", "expenses", "legislatures"]:
            assert expected in tables

    def test_stats_all_zero(self, store: HistoryStore) -> None:
        s = store.stats()
        for v in s.values():
            assert v == 0


# ---------------------------------------------------------------------------
# Politicians
# ---------------------------------------------------------------------------


class TestPoliticianStore:
    def test_upsert_and_get(self, store: HistoryStore) -> None:
        p = _politician()
        store.upsert_politician(p)
        fetched = store.get_politician(p.id)
        assert fetched is not None
        assert fetched.name == p.name
        assert fetched.wikidata_id == p.wikidata_id

    def test_upsert_replaces(self, store: HistoryStore) -> None:
        p = _politician()
        store.upsert_politician(p)
        p.summary = "Updated summary"
        store.upsert_politician(p)
        fetched = store.get_politician(p.id)
        assert fetched.summary == "Updated summary"
        assert store.count_politicians() == 1

    def test_get_nonexistent_returns_none(self, store: HistoryStore) -> None:
        assert store.get_politician("wikidata:Q000000") is None

    def test_upsert_many(self, store: HistoryStore) -> None:
        politicians = [_politician(name=f"Person {i}", wikidata_id=f"Q{i}") for i in range(5)]
        saved = store.upsert_politicians(politicians)
        assert saved == 5
        assert store.count_politicians() == 5

    def test_search_by_name(self, store: HistoryStore) -> None:
        store.upsert_politician(_politician(name="Lula da Silva"))
        store.upsert_politician(_politician(name="Bolsonaro", wikidata_id="Q99002"))
        results = store.search_politicians("Lula")
        assert len(results) == 1
        assert results[0].name == "Lula da Silva"

    def test_search_no_match(self, store: HistoryStore) -> None:
        store.upsert_politician(_politician())
        assert store.search_politicians("XYZ_NOBODY") == []

    def test_roles_roundtrip(self, store: HistoryStore) -> None:
        p = _politician()
        p.roles = [
            PoliticianRole(role="Ministro do STF", institution="stf", start_date="2017-03-22")
        ]
        store.upsert_politician(p)
        fetched = store.get_politician(p.id)
        assert len(fetched.roles) == 1
        assert fetched.roles[0].role == "Ministro do STF"
        assert fetched.roles[0].institution == "stf"

    def test_list_politicians(self, store: HistoryStore) -> None:
        for i in range(3):
            store.upsert_politician(_politician(name=f"Person {i}", wikidata_id=f"Q{i+100}"))
        listing = store.list_politicians(limit=10)
        assert len(listing) == 3


# ---------------------------------------------------------------------------
# Historical Events
# ---------------------------------------------------------------------------


class TestEventStore:
    def test_upsert_and_get(self, store: HistoryStore) -> None:
        e = _event()
        store.upsert_event(e)
        fetched = store.get_event(e.id)
        assert fetched is not None
        assert fetched.title == e.title

    def test_upsert_replaces(self, store: HistoryStore) -> None:
        e = _event()
        store.upsert_event(e)
        e.summary = "New summary"
        store.upsert_event(e)
        assert store.count_events() == 1
        assert store.get_event(e.id).summary == "New summary"

    def test_get_nonexistent_returns_none(self, store: HistoryStore) -> None:
        assert store.get_event("event:notexist") is None

    def test_upsert_many(self, store: HistoryStore) -> None:
        events = [_event(title=f"Event {i}", wikidata_id=f"Q{i+200}") for i in range(4)]
        saved = store.upsert_events(events)
        assert saved == 4
        assert store.count_events() == 4

    def test_search_by_title(self, store: HistoryStore) -> None:
        store.upsert_event(_event(title="Operação Lava Jato"))
        store.upsert_event(_event(title="Impeachment Dilma", wikidata_id="Q300"))
        results = store.search_events("Lava Jato")
        assert len(results) == 1
        assert "Lava" in results[0].title

    def test_actors_roundtrip(self, store: HistoryStore) -> None:
        e = _event()
        e.actors = ["camara:100", "wikidata:Q9999"]
        e.institutions = ["stf", "mpf"]
        store.upsert_event(e)
        fetched = store.get_event(e.id)
        assert fetched.actors == ["camara:100", "wikidata:Q9999"]
        assert fetched.institutions == ["stf", "mpf"]


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------


class TestVoteStore:
    def test_upsert_and_query(self, store: HistoryStore) -> None:
        v = _vote()
        store.upsert_votes([v])
        results = store.get_deputy_votes("camara:100")
        assert len(results) == 1
        assert results[0].vote == "SIM"

    def test_multiple_votes_same_deputy(self, store: HistoryStore) -> None:
        v1 = _vote(proposition_id="camara:prop:1", session_id="s1")
        v2 = _vote(proposition_id="camara:prop:2", session_id="s2")
        store.upsert_votes([v1, v2])
        results = store.get_deputy_votes("camara:100")
        assert len(results) == 2

    def test_proposition_votes(self, store: HistoryStore) -> None:
        v1 = _vote(deputy_id="camara:1", session_id="s1")
        v2 = _vote(deputy_id="camara:2", session_id="s2")
        store.upsert_votes([v1, v2])
        results = store.get_proposition_votes("camara:prop:500")
        assert len(results) == 2

    def test_count(self, store: HistoryStore) -> None:
        store.upsert_votes([_vote(proposition_id=f"camara:prop:{i}", session_id=f"s{i}") for i in range(5)])
        assert store.count_votes() == 5


# ---------------------------------------------------------------------------
# Election Results
# ---------------------------------------------------------------------------


class TestElectionResultStore:
    def test_upsert_and_search(self, store: HistoryStore) -> None:
        r = _election_result()
        store.upsert_election_results([r])
        results = store.search_election_results(candidate_name="Candidato Teste")
        assert len(results) == 1
        assert results[0].elected is True

    def test_filter_by_year(self, store: HistoryStore) -> None:
        store.upsert_election_results([
            _election_result(year=2018, candidate_name="Alpha", party="PT"),
            _election_result(year=2022, candidate_name="Beta", party="PL"),
        ])
        r2018 = store.search_election_results(year=2018)
        assert len(r2018) == 1
        assert r2018[0].year == 2018

    def test_filter_elected_only(self, store: HistoryStore) -> None:
        store.upsert_election_results([
            _election_result(elected=True, candidate_name="Winner", party="PT"),
            _election_result(elected=False, candidate_name="Loser", party="PL"),
        ])
        elected = store.search_election_results(elected_only=True)
        assert all(r.elected for r in elected)

    def test_count(self, store: HistoryStore) -> None:
        store.upsert_election_results([_election_result(candidate_name=f"C{i}", party="PT") for i in range(3)])
        assert store.count_election_results() == 3


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


class TestExpenseStore:
    def test_upsert_and_get(self, store: HistoryStore) -> None:
        e = _expense()
        store.upsert_expenses([e])
        results = store.get_deputy_expenses("camara:100")
        assert len(results) == 1
        assert results[0].value == 1200.50

    def test_filter_by_year(self, store: HistoryStore) -> None:
        store.upsert_expenses([
            _expense(year=2022, month=1, document_number="A"),
            _expense(year=2023, month=6, document_number="B"),
        ])
        results = store.get_deputy_expenses("camara:100", year=2022)
        assert len(results) == 1
        assert results[0].year == 2022

    def test_top_spenders(self, store: HistoryStore) -> None:
        store.upsert_expenses([
            _expense(deputy_id="camara:1", deputy_name="High Spender", value=5000.0, document_number="X"),
            _expense(deputy_id="camara:2", deputy_name="Low Spender", value=100.0, document_number="Y"),
        ])
        top = store.top_spenders(limit=5)
        assert top[0]["deputy_name"] == "High Spender"
        assert top[0]["total_spent"] == 5000.0

    def test_count(self, store: HistoryStore) -> None:
        store.upsert_expenses([_expense(document_number=f"D{i}") for i in range(4)])
        assert store.count_expenses() == 4


# ---------------------------------------------------------------------------
# Legislatures
# ---------------------------------------------------------------------------


class TestLegislatureStore:
    def test_upsert_and_list(self, store: HistoryStore) -> None:
        leg = Legislature(id=57, start_date="2023-02-01", description="57ª Legislatura")
        store.upsert_legislature(leg)
        legs = store.list_legislatures()
        assert len(legs) == 1
        assert legs[0].id == 57

    def test_upsert_many(self, store: HistoryStore) -> None:
        legs = [
            Legislature(id=55, start_date="2015-02-01", description="55ª"),
            Legislature(id=56, start_date="2019-02-01", description="56ª"),
            Legislature(id=57, start_date="2023-02-01", description="57ª"),
        ]
        count = store.upsert_legislatures(legs)
        assert count == 3
        listing = store.list_legislatures()
        assert len(listing) == 3
        # Should be DESC order
        assert listing[0].id == 57


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_after_inserts(self, store: HistoryStore) -> None:
        store.upsert_politician(_politician())
        store.upsert_event(_event())
        store.upsert_votes([_vote()])
        store.upsert_election_results([_election_result()])
        store.upsert_expenses([_expense()])
        store.upsert_legislature(Legislature(id=57, start_date="2023-02-01"))

        s = store.stats()
        assert s["politicians"] == 1
        assert s["historical_events"] == 1
        assert s["votes"] == 1
        assert s["election_results"] == 1
        assert s["expenses"] == 1
        assert s["legislatures"] == 1
