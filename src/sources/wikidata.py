"""
Wikidata SPARQL client for Brazilian political data.

Uses the public Wikidata Query Service — no API key required.
Endpoint: https://query.wikidata.org/sparql

Key Wikidata entity QIDs used:
  Q155       — Brazil (country)
  Q82955     — politician (occupation)
  Q10302614  — Minister of the Supreme Federal Tribunal (STF)
  Q21609546  — Federal Deputy of Brazil (Deputado Federal)
  Q18611017  — Senator of Brazil (Senador Federal)
  Q35137     — President of Brazil (Presidente da República)
  Q5055441   — Governor (Governador de estado brasileiro)
  Q15238777  — legislature (generic — used to find legislative terms)

Rate limit: ~5–10 req/s. All methods sleep briefly between requests.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from src.history.models import HistoricalEvent, Legislature, Politician, PoliticianRole

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "AntiCorrupt/1.0 (https://github.com/nandorv/anti_corrupt) Python/httpx",
}
_TIMEOUT = 45.0
_SLEEP = 0.5  # seconds between requests


class WikidataError(Exception):
    """Raised when a Wikidata SPARQL request fails."""


class WikidataClient:
    """
    Client for querying the Wikidata SPARQL endpoint.

    All public methods return parsed model objects ready to be saved
    to the HistoryStore.
    """

    def __init__(self, timeout: float = _TIMEOUT):
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(self, sparql: str) -> list[dict]:
        """Execute SPARQL and return the results bindings as a list of dicts."""
        try:
            response = self._client.get(
                SPARQL_ENDPOINT,
                params={"query": sparql, "format": "json"},
            )
            response.raise_for_status()
            return response.json().get("results", {}).get("bindings", [])
        except httpx.HTTPError as exc:
            raise WikidataError(f"Wikidata SPARQL request failed: {exc}") from exc

    @staticmethod
    def _val(binding: dict, key: str) -> Optional[str]:
        """Safely extract the string value from a SPARQL binding."""
        entry = binding.get(key)
        if entry is None:
            return None
        return entry.get("value")

    @staticmethod
    def _wid(uri: str) -> Optional[str]:
        """Extract the QID (e.g. Q12345) from a Wikidata entity URI."""
        if not uri:
            return None
        return uri.split("/")[-1] or None

    @staticmethod
    def _date(raw: Optional[str]) -> Optional[str]:
        """Trim a Wikidata date string to YYYY-MM-DD."""
        if not raw:
            return None
        return raw[:10]

    @staticmethod
    def _is_qid(label: str) -> bool:
        """Return True if the label is just a bare QID fallback (e.g. 'Q12345')."""
        return bool(label) and label.startswith("Q") and label[1:].isdigit()

    # ------------------------------------------------------------------
    # Specific position fetchers
    # ------------------------------------------------------------------

    def fetch_stf_ministers(self) -> list[Politician]:
        """Fetch all STF ministers (current and historical) from Wikidata."""
        sparql = """
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?startDate ?endDate ?description
        WHERE {
          ?person p:P39 ?stmt .
          ?stmt ps:P39 wd:Q10302614 .
          OPTIONAL { ?stmt pq:P580 ?startDate }
          OPTIONAL { ?stmt pq:P582 ?endDate }
          OPTIONAL { ?person wdt:P569 ?birthDate }
          OPTIONAL { ?person wdt:P19 ?birthPlace }
          OPTIONAL {
            ?person schema:description ?description
            FILTER(LANG(?description) = "pt")
          }
          SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
        }
        ORDER BY ?personLabel
        """
        bindings = self._query(sparql)
        politicians: dict[str, Politician] = {}

        for b in bindings:
            wid = self._wid(self._val(b, "person") or "")
            if not wid:
                continue
            name = self._val(b, "personLabel") or ""
            if self._is_qid(name):
                continue

            if wid not in politicians:
                politicians[wid] = Politician(
                    wikidata_id=wid,
                    name=name,
                    birth_date=self._date(self._val(b, "birthDate")),
                    birth_place=self._val(b, "birthPlaceLabel"),
                    roles=[],
                    tags=["stf", "judiciário", "ministro"],
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )

            politicians[wid].roles.append(
                PoliticianRole(
                    role="Ministro do STF",
                    institution="stf",
                    start_date=self._date(self._val(b, "startDate")),
                    end_date=self._date(self._val(b, "endDate")),
                )
            )

        time.sleep(_SLEEP)
        return list(politicians.values())

    def fetch_politicians_by_position(
        self,
        position_qid: str,
        role_name: str,
        institution: str,
        tags: list[str],
        limit: int = 500,
    ) -> list[Politician]:
        """
        Generic fetcher for any Brazilian political position by Wikidata QID.

        Args:
            position_qid: Wikidata QID for the position (e.g. "Q21609546")
            role_name:     Human-readable role label in Portuguese
            institution:   Institution slug (e.g. "camara-deputados")
            tags:          List of tags to apply to all results
            limit:         Max number of people to return
        """
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?startDate ?endDate ?description
        WHERE {{
          ?person p:P39 ?stmt .
          ?stmt ps:P39 wd:{position_qid} .
          OPTIONAL {{ ?stmt pq:P580 ?startDate }}
          OPTIONAL {{ ?stmt pq:P582 ?endDate }}
          OPTIONAL {{ ?person wdt:P569 ?birthDate }}
          OPTIONAL {{ ?person wdt:P19 ?birthPlace }}
          OPTIONAL {{ ?person wdt:P102 ?party }}
          OPTIONAL {{
            ?person schema:description ?description
            FILTER(LANG(?description) = "pt")
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" }}
        }}
        ORDER BY ?personLabel
        LIMIT {limit}
        """
        bindings = self._query(sparql)
        politicians: dict[str, Politician] = {}

        for b in bindings:
            wid = self._wid(self._val(b, "person") or "")
            if not wid:
                continue
            name = self._val(b, "personLabel") or ""
            if self._is_qid(name):
                continue

            if wid not in politicians:
                politicians[wid] = Politician(
                    wikidata_id=wid,
                    name=name,
                    birth_date=self._date(self._val(b, "birthDate")),
                    birth_place=self._val(b, "birthPlaceLabel"),
                    party=self._val(b, "partyLabel"),
                    roles=[],
                    tags=list(tags),
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )

            politicians[wid].roles.append(
                PoliticianRole(
                    role=role_name,
                    institution=institution,
                    start_date=self._date(self._val(b, "startDate")),
                    end_date=self._date(self._val(b, "endDate")),
                )
            )

        time.sleep(_SLEEP)
        return list(politicians.values())

    def fetch_federal_deputies(self, limit: int = 600) -> list[Politician]:
        """Fetch all Brazilian Federal Deputies (current + historical)."""
        return self.fetch_politicians_by_position(
            "Q21609546",
            "Deputado Federal",
            "camara-deputados",
            ["câmara", "deputado-federal", "legislativo"],
            limit=limit,
        )

    def fetch_senators(self, limit: int = 300) -> list[Politician]:
        """Fetch all Brazilian Senators (current + historical)."""
        return self.fetch_politicians_by_position(
            "Q18611017",
            "Senador Federal",
            "senado-federal",
            ["senado", "senador", "legislativo"],
            limit=limit,
        )

    def fetch_presidents(self) -> list[Politician]:
        """Fetch all Presidents of Brazil."""
        return self.fetch_politicians_by_position(
            "Q35137",
            "Presidente da República",
            "presidencia-da-republica",
            ["presidente", "executivo"],
            limit=50,
        )

    def fetch_governors(self, limit: int = 300) -> list[Politician]:
        """Fetch all Brazilian state governors."""
        return self.fetch_politicians_by_position(
            "Q5055441",
            "Governador",
            "governo-estadual",
            ["governador", "executivo-estadual"],
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Search (for targeted individual lookup)
    # ------------------------------------------------------------------

    def search_person(self, name: str, limit: int = 10) -> list[Politician]:
        """
        Search Wikidata for a Brazilian public figure by name.
        Returns the top matches with basic biographical data.
        """
        # Escape double quotes in the name to avoid SPARQL injection
        safe_name = name.replace('"', "")
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?description
        WHERE {{
          ?person wdt:P31 wd:Q5 ;
                  wdt:P27 wd:Q155 .
          OPTIONAL {{ ?person wdt:P569 ?birthDate }}
          OPTIONAL {{ ?person wdt:P19 ?birthPlace }}
          OPTIONAL {{ ?person wdt:P102 ?party }}
          OPTIONAL {{
            ?person schema:description ?description
            FILTER(LANG(?description) = "pt")
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" }}
          FILTER(CONTAINS(LCASE(STR(?personLabel)), LCASE("{safe_name}")))
        }}
        LIMIT {limit}
        """
        bindings = self._query(sparql)
        politicians = []
        for b in bindings:
            wid = self._wid(self._val(b, "person") or "")
            if not wid:
                continue
            name_label = self._val(b, "personLabel") or ""
            if self._is_qid(name_label):
                continue
            birth = self._val(b, "birthDate")
            politicians.append(
                Politician(
                    wikidata_id=wid,
                    name=name_label,
                    birth_date=self._date(birth),
                    birth_place=self._val(b, "birthPlaceLabel"),
                    party=self._val(b, "partyLabel"),
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )
            )
        time.sleep(_SLEEP)
        return politicians

    # ------------------------------------------------------------------
    # Historical events
    # ------------------------------------------------------------------

    def fetch_political_events(self, limit: int = 150) -> list[HistoricalEvent]:
        """
        Fetch major Brazilian political events from Wikidata.
        Includes political scandals, elections, and crises.
        """
        sparql = f"""
        SELECT DISTINCT ?event ?eventLabel ?date ?description
        WHERE {{
          ?event wdt:P17 wd:Q155 .
          {{
            {{ ?event wdt:P31 wd:Q2334719 }}  # political scandal
            UNION {{ ?event wdt:P31 wd:Q40231 }}    # election
            UNION {{ ?event wdt:P31 wd:Q3307126 }}  # political crisis
            UNION {{ ?event wdt:P31 wd:Q1371582 }}  # political movement
          }}
          OPTIONAL {{ ?event wdt:P585 ?date }}
          OPTIONAL {{
            ?event schema:description ?description
            FILTER(LANG(?description) = "pt")
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" }}
        }}
        ORDER BY DESC(?date)
        LIMIT {limit}
        """
        bindings = self._query(sparql)
        events: list[HistoricalEvent] = []
        seen: set[str] = set()

        for b in bindings:
            wid = self._wid(self._val(b, "event") or "")
            if not wid or wid in seen:
                continue
            seen.add(wid)
            title = self._val(b, "eventLabel") or ""
            if self._is_qid(title):
                continue
            date_raw = self._val(b, "date")
            events.append(
                HistoricalEvent(
                    wikidata_id=wid,
                    title=title,
                    date=self._date(date_raw),
                    type="event",
                    summary=self._val(b, "description") or "",
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                )
            )

        time.sleep(_SLEEP)
        return events

    # ------------------------------------------------------------------
    # Legislature terms
    # ------------------------------------------------------------------

    def fetch_legislatures(self) -> list[Legislature]:
        """Fetch Brazilian legislative term metadata from Wikidata."""
        sparql = """
        SELECT ?item ?itemLabel ?startDate ?endDate ?ordinal
        WHERE {
          ?item wdt:P31 wd:Q15238777 ;
                wdt:P17 wd:Q155 .
          OPTIONAL { ?item wdt:P580 ?startDate }
          OPTIONAL { ?item wdt:P582 ?endDate }
          OPTIONAL { ?item wdt:P1545 ?ordinal }
          SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
        }
        ORDER BY ?startDate
        """
        bindings = self._query(sparql)
        legislatures: list[Legislature] = []
        seen: set[str] = set()
        counter = 1

        for b in bindings:
            wid = self._wid(self._val(b, "item") or "")
            if not wid or wid in seen:
                continue
            seen.add(wid)
            start_raw = self._val(b, "startDate")
            if not start_raw:
                continue
            end_raw = self._val(b, "endDate")
            ordinal_raw = self._val(b, "ordinal")
            try:
                leg_id = int(ordinal_raw) if ordinal_raw and ordinal_raw.isdigit() else counter
                legislatures.append(
                    Legislature(
                        id=leg_id,
                        start_date=start_raw[:10],
                        end_date=end_raw[:10] if end_raw else None,
                        description=self._val(b, "itemLabel") or f"Legislatura {leg_id}",
                    )
                )
                counter += 1
            except Exception as exc:
                logger.debug("Skipping legislature record: %s", exc)

        time.sleep(_SLEEP)
        return legislatures

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "WikidataClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
