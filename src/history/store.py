"""
SQLite-backed historical database.

Tables:
  politicians       — deduplicated by id (wikidata:Q... or camara:N)
  historical_events — major political events
  votes             — individual deputy votes on propositions
  election_results  — TSE results per candidate per election
  expenses          — CEAP expense records per deputy
  legislatures      — legislative term metadata
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import sqlite_utils

from src.history.models import (
    Expense,
    HistoricalEvent,
    Legislature,
    Politician,
    PoliticianRole,
    Vote,
    ElectionResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(os.getenv("OUTPUT_DIR", "output")) / "history.db"


# ---------------------------------------------------------------------------
# HistoryStore
# ---------------------------------------------------------------------------


class HistoryStore:
    """
    SQLite store for all historical political data.

    Uses sqlite-utils with insert(replace=True) for idempotent upserts.
    All JSON fields (lists, dicts) are serialised as JSON strings.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite_utils.Database(str(db_path))
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        db = self._db

        if "politicians" not in db.table_names():
            db["politicians"].create(
                {
                    "id": str,
                    "name": str,
                    "birth_date": str,
                    "birth_place": str,
                    "death_date": str,
                    "party": str,
                    "state": str,
                    "wikidata_id": str,
                    "camara_id": int,
                    "tse_id": str,
                    "summary": str,
                    "tags": str,       # JSON list
                    "sources": str,    # JSON list
                    "roles": str,      # JSON list of {role, institution, ...}
                    "education": str,  # JSON list
                    "fetched_at": str,
                },
                pk="id",
            )
            db["politicians"].create_index(["name"])
            db["politicians"].create_index(["wikidata_id"])
            db["politicians"].create_index(["camara_id"])

        if "historical_events" not in db.table_names():
            db["historical_events"].create(
                {
                    "id": str,
                    "title": str,
                    "date": str,
                    "end_date": str,
                    "type": str,
                    "summary": str,
                    "detailed_description": str,
                    "significance": str,
                    "actors": str,         # JSON list
                    "institutions": str,   # JSON list
                    "related_events": str, # JSON list
                    "tags": str,           # JSON list
                    "sources": str,        # JSON list
                    "wikidata_id": str,
                    "fetched_at": str,
                },
                pk="id",
            )
            db["historical_events"].create_index(["date"])
            db["historical_events"].create_index(["type"])

        if "votes" not in db.table_names():
            db["votes"].create(
                {
                    "id": str,
                    "deputy_id": str,
                    "deputy_camara_id": int,
                    "deputy_name": str,
                    "proposition_id": str,
                    "proposition_title": str,
                    "proposition_type": str,
                    "vote": str,
                    "date": str,
                    "session_id": str,
                    "party": str,
                    "state": str,
                    "fetched_at": str,
                },
                pk="id",
            )
            db["votes"].create_index(["deputy_id"])
            db["votes"].create_index(["proposition_id"])
            db["votes"].create_index(["date"])

        if "election_results" not in db.table_names():
            db["election_results"].create(
                {
                    "id": str,
                    "year": int,
                    "state": str,
                    "municipality": str,
                    "position": str,
                    "candidate_name": str,
                    "candidate_number": str,
                    "candidate_cpf": str,
                    "party": str,
                    "coalition": str,
                    "votes": int,
                    "elected": int,      # 0 or 1
                    "round": int,
                    "tse_seq_candidate": str,
                    "fetched_at": str,
                },
                pk="id",
            )
            db["election_results"].create_index(["year", "state"])
            db["election_results"].create_index(["candidate_name"])
            db["election_results"].create_index(["party"])

        if "expenses" not in db.table_names():
            db["expenses"].create(
                {
                    "id": str,
                    "deputy_id": str,
                    "deputy_camara_id": int,
                    "deputy_name": str,
                    "year": int,
                    "month": int,
                    "category": str,
                    "supplier": str,
                    "supplier_cnpj_cpf": str,
                    "value": float,
                    "document_number": str,
                    "description": str,
                    "fetched_at": str,
                },
                pk="id",
            )
            db["expenses"].create_index(["deputy_id"])
            db["expenses"].create_index(["year", "month"])

        if "legislatures" not in db.table_names():
            db["legislatures"].create(
                {
                    "id": int,
                    "start_date": str,
                    "end_date": str,
                    "description": str,
                    "fetched_at": str,
                },
                pk="id",
            )

    # ------------------------------------------------------------------
    # Politicians
    # ------------------------------------------------------------------

    def _pol_to_row(self, p: Politician) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "birth_date": p.birth_date,
            "birth_place": p.birth_place,
            "death_date": p.death_date,
            "party": p.party,
            "state": p.state,
            "wikidata_id": p.wikidata_id,
            "camara_id": p.camara_id,
            "tse_id": p.tse_id,
            "summary": p.summary,
            "tags": json.dumps(p.tags, ensure_ascii=False),
            "sources": json.dumps(p.sources, ensure_ascii=False),
            "roles": json.dumps([r.model_dump() for r in p.roles], ensure_ascii=False),
            "education": json.dumps(p.education, ensure_ascii=False),
            "fetched_at": p.fetched_at.isoformat(),
        }

    def _row_to_pol(self, row: dict) -> Politician:
        row = dict(row)
        row["tags"] = json.loads(row.get("tags") or "[]")
        row["sources"] = json.loads(row.get("sources") or "[]")
        raw_roles = json.loads(row.get("roles") or "[]")
        row["roles"] = [PoliticianRole(**r) for r in raw_roles]
        row["education"] = json.loads(row.get("education") or "[]")
        if isinstance(row.get("fetched_at"), str):
            row["fetched_at"] = dt.datetime.fromisoformat(row["fetched_at"])
        return Politician(**row)

    def upsert_politician(self, p: Politician) -> None:
        self._db["politicians"].insert(self._pol_to_row(p), replace=True)

    def upsert_politicians(self, politicians: list[Politician]) -> int:
        if not politicians:
            return 0
        rows = [self._pol_to_row(p) for p in politicians]
        self._db["politicians"].insert_all(rows, replace=True)
        return len(rows)

    def get_politician(self, pol_id: str) -> Optional[Politician]:
        try:
            row = dict(self._db["politicians"].get(pol_id))
            return self._row_to_pol(row)
        except Exception:
            return None

    def search_politicians(self, query: str, limit: int = 20) -> list[Politician]:
        rows = list(
            self._db["politicians"].rows_where(
                "name LIKE ? OR summary LIKE ?",
                [f"%{query}%", f"%{query}%"],
                limit=limit,
                order_by="name",
            )
        )
        return [self._row_to_pol(r) for r in rows]

    def list_politicians(self, limit: int = 100, offset: int = 0) -> list[Politician]:
        rows = list(
            self._db.execute(
                "SELECT * FROM politicians ORDER BY name LIMIT ? OFFSET ?",
                [limit, offset],
            ).fetchall()
        )
        if not rows:
            return []
        cols = [d[1] for d in self._db.execute("PRAGMA table_info(politicians)").fetchall()]
        return [self._row_to_pol(dict(zip(cols, row))) for row in rows]

    def count_politicians(self) -> int:
        return self._db["politicians"].count

    # ------------------------------------------------------------------
    # Historical Events
    # ------------------------------------------------------------------

    def _event_to_row(self, e: HistoricalEvent) -> dict:
        return {
            "id": e.id,
            "title": e.title,
            "date": e.date,
            "end_date": e.end_date,
            "type": e.type,
            "summary": e.summary,
            "detailed_description": e.detailed_description,
            "significance": e.significance,
            "actors": json.dumps(e.actors, ensure_ascii=False),
            "institutions": json.dumps(e.institutions, ensure_ascii=False),
            "related_events": json.dumps(e.related_events, ensure_ascii=False),
            "tags": json.dumps(e.tags, ensure_ascii=False),
            "sources": json.dumps(e.sources, ensure_ascii=False),
            "wikidata_id": e.wikidata_id,
            "fetched_at": e.fetched_at.isoformat(),
        }

    def _row_to_event(self, row: dict) -> HistoricalEvent:
        row = dict(row)
        for field in ("actors", "institutions", "related_events", "tags", "sources"):
            row[field] = json.loads(row.get(field) or "[]")
        if isinstance(row.get("fetched_at"), str):
            row["fetched_at"] = dt.datetime.fromisoformat(row["fetched_at"])
        return HistoricalEvent(**row)

    def upsert_event(self, e: HistoricalEvent) -> None:
        self._db["historical_events"].insert(self._event_to_row(e), replace=True)

    def upsert_events(self, events: list[HistoricalEvent]) -> int:
        if not events:
            return 0
        rows = [self._event_to_row(e) for e in events]
        self._db["historical_events"].insert_all(rows, replace=True)
        return len(rows)

    def get_event(self, event_id: str) -> Optional[HistoricalEvent]:
        try:
            row = dict(self._db["historical_events"].get(event_id))
            return self._row_to_event(row)
        except Exception:
            return None

    def search_events(self, query: str, limit: int = 20) -> list[HistoricalEvent]:
        rows = list(
            self._db["historical_events"].rows_where(
                "title LIKE ? OR summary LIKE ?",
                [f"%{query}%", f"%{query}%"],
                limit=limit,
                order_by="date desc",
            )
        )
        return [self._row_to_event(r) for r in rows]

    def count_events(self) -> int:
        return self._db["historical_events"].count

    # ------------------------------------------------------------------
    # Votes
    # ------------------------------------------------------------------

    def _vote_to_row(self, v: Vote) -> dict:
        return {
            "id": v.id,
            "deputy_id": v.deputy_id,
            "deputy_camara_id": v.deputy_camara_id,
            "deputy_name": v.deputy_name,
            "proposition_id": v.proposition_id,
            "proposition_title": v.proposition_title,
            "proposition_type": v.proposition_type,
            "vote": v.vote,
            "date": v.date,
            "session_id": v.session_id,
            "party": v.party,
            "state": v.state,
            "fetched_at": v.fetched_at.isoformat(),
        }

    def upsert_votes(self, votes: list[Vote]) -> int:
        if not votes:
            return 0
        rows = [self._vote_to_row(v) for v in votes]
        self._db["votes"].insert_all(rows, replace=True)
        return len(rows)

    def get_deputy_votes(self, deputy_id: str, limit: int = 100) -> list[Vote]:
        rows = list(
            self._db["votes"].rows_where(
                "deputy_id = ?",
                [deputy_id],
                limit=limit,
                order_by="date desc",
            )
        )
        result = []
        for row in rows:
            row = dict(row)
            if isinstance(row.get("fetched_at"), str):
                row["fetched_at"] = dt.datetime.fromisoformat(row["fetched_at"])
            result.append(Vote(**row))
        return result

    def get_proposition_votes(self, proposition_id: str) -> list[Vote]:
        rows = list(
            self._db["votes"].rows_where(
                "proposition_id = ?",
                [proposition_id],
                order_by="deputy_name",
            )
        )
        result = []
        for row in rows:
            row = dict(row)
            if isinstance(row.get("fetched_at"), str):
                row["fetched_at"] = dt.datetime.fromisoformat(row["fetched_at"])
            result.append(Vote(**row))
        return result

    def count_votes(self) -> int:
        return self._db["votes"].count

    # ------------------------------------------------------------------
    # Election Results
    # ------------------------------------------------------------------

    def _result_to_row(self, r: ElectionResult) -> dict:
        return {
            "id": r.id,
            "year": r.year,
            "state": r.state,
            "municipality": r.municipality,
            "position": r.position,
            "candidate_name": r.candidate_name,
            "candidate_number": r.candidate_number,
            "candidate_cpf": r.candidate_cpf,
            "party": r.party,
            "coalition": r.coalition,
            "votes": r.votes,
            "elected": int(r.elected),
            "round": r.round,
            "tse_seq_candidate": r.tse_seq_candidate,
            "fetched_at": r.fetched_at.isoformat(),
        }

    def upsert_election_results(self, results: list[ElectionResult]) -> int:
        if not results:
            return 0
        rows = [self._result_to_row(r) for r in results]
        self._db["election_results"].insert_all(rows, replace=True)
        return len(rows)

    def search_election_results(
        self,
        candidate_name: Optional[str] = None,
        year: Optional[int] = None,
        state: Optional[str] = None,
        position: Optional[str] = None,
        party: Optional[str] = None,
        elected_only: bool = False,
        limit: int = 100,
    ) -> list[ElectionResult]:
        conditions: list[str] = []
        params: list[Any] = []

        if candidate_name:
            conditions.append("candidate_name LIKE ?")
            params.append(f"%{candidate_name}%")
        if year:
            conditions.append("year = ?")
            params.append(year)
        if state:
            conditions.append("state = ?")
            params.append(state.upper())
        if position:
            conditions.append("position LIKE ?")
            params.append(f"%{position.upper()}%")
        if party:
            conditions.append("party = ?")
            params.append(party.upper())
        if elected_only:
            conditions.append("elected = 1")

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM election_results WHERE {where} ORDER BY votes DESC LIMIT ?",
            params,
        ).fetchall()
        cols = [d[1] for d in self._db.execute("PRAGMA table_info(election_results)").fetchall()]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["elected"] = bool(d["elected"])
            if isinstance(d.get("fetched_at"), str):
                d["fetched_at"] = dt.datetime.fromisoformat(d["fetched_at"])
            result.append(ElectionResult(**d))
        return result

    def count_election_results(self) -> int:
        return self._db["election_results"].count

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------

    def _expense_to_row(self, e: Expense) -> dict:
        return {
            "id": e.id,
            "deputy_id": e.deputy_id,
            "deputy_camara_id": e.deputy_camara_id,
            "deputy_name": e.deputy_name,
            "year": e.year,
            "month": e.month,
            "category": e.category,
            "supplier": e.supplier,
            "supplier_cnpj_cpf": e.supplier_cnpj_cpf,
            "value": e.value,
            "document_number": e.document_number,
            "description": e.description,
            "fetched_at": e.fetched_at.isoformat(),
        }

    def upsert_expenses(self, expenses: list[Expense]) -> int:
        if not expenses:
            return 0
        rows = [self._expense_to_row(e) for e in expenses]
        self._db["expenses"].insert_all(rows, replace=True)
        return len(rows)

    def get_deputy_expenses(
        self, deputy_id: str, year: Optional[int] = None, limit: int = 200
    ) -> list[Expense]:
        conditions = ["deputy_id = ?"]
        params: list[Any] = [deputy_id]
        if year:
            conditions.append("year = ?")
            params.append(year)
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM expenses WHERE {' AND '.join(conditions)} "
            f"ORDER BY year DESC, month DESC LIMIT ?",
            params,
        ).fetchall()
        cols = [d[1] for d in self._db.execute("PRAGMA table_info(expenses)").fetchall()]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d.get("fetched_at"), str):
                d["fetched_at"] = dt.datetime.fromisoformat(d["fetched_at"])
            result.append(Expense(**d))
        return result

    def top_spenders(self, year: Optional[int] = None, limit: int = 20) -> list[dict]:
        """Return deputies sorted by total CEAP spending."""
        where = "WHERE year = ?" if year else ""
        params: list[Any] = []
        if year:
            params.append(year)
        params.append(limit)
        rows = self._db.execute(
            f"""
            SELECT deputy_id, deputy_name, SUM(value) as total_spent, COUNT(*) as records
            FROM expenses {where}
            GROUP BY deputy_id, deputy_name
            ORDER BY total_spent DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "deputy_id": r[0],
                "deputy_name": r[1],
                "total_spent": round(r[2], 2),
                "records": r[3],
            }
            for r in rows
        ]

    def count_expenses(self) -> int:
        return self._db["expenses"].count

    # ------------------------------------------------------------------
    # Legislatures
    # ------------------------------------------------------------------

    def upsert_legislature(self, leg: Legislature) -> None:
        self._db["legislatures"].insert(
            {
                "id": leg.id,
                "start_date": leg.start_date,
                "end_date": leg.end_date,
                "description": leg.description,
                "fetched_at": leg.fetched_at.isoformat(),
            },
            replace=True,
        )

    def upsert_legislatures(self, legs: list[Legislature]) -> int:
        for leg in legs:
            self.upsert_legislature(leg)
        return len(legs)

    def list_legislatures(self) -> list[Legislature]:
        rows = self._db.execute("SELECT * FROM legislatures ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            d = {"id": row[0], "start_date": row[1], "end_date": row[2], "description": row[3]}
            if row[4]:
                d["fetched_at"] = dt.datetime.fromisoformat(row[4])
            result.append(Legislature(**d))
        return result

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in [
            "politicians",
            "historical_events",
            "votes",
            "election_results",
            "expenses",
            "legislatures",
        ]:
            try:
                counts[table] = self._db[table].count
            except Exception:
                counts[table] = 0
        return counts
