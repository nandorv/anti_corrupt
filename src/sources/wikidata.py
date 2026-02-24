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
_TIMEOUT = 90.0  # seconds — complex Wikidata SPARQL queries can take 60–80s
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
                        ?description
        WHERE {
          { ?person wdt:P39 wd:Q10302614 }
          UNION
          { ?person p:P39 ?stmt . ?stmt ps:P39 wd:Q10302614 }
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
                    roles=[PoliticianRole(role="Ministro do STF", institution="stf")],
                    tags=["stf", "judiciário", "ministro"],
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )

        time.sleep(_SLEEP)

        # Fallback: QID might be wrong — use description-based search
        if not politicians:
            logger.info("STF QID returned 0 — using description fallback")
            fallback = self._fetch_by_description_filter(
                filter_regex="ministro.*supremo|ministro.*stf|supremo tribunal federal",
                role_name="Ministro do STF",
                institution="stf",
                tags=["stf", "judiciário", "ministro"],
                limit=50,
            )
            for p in fallback:
                politicians[p.id] = p

        return list(politicians.values())

    def fetch_politicians_by_position(
        self,
        position_qid: str,
        role_name: str,
        institution: str,
        tags: list[str],
        limit: int = 500,
        since_year: Optional[int] = None,
    ) -> list[Politician]:
        """
        Generic fetcher for any Brazilian political position by Wikidata QID.

        Args:
            position_qid: Wikidata QID for the position (e.g. "Q21609546")
            role_name:     Human-readable role label in Portuguese
            institution:   Institution slug (e.g. "camara-deputados")
            tags:          List of tags to apply to all results
            limit:         Max number of people to return
            since_year:    If set, only include people whose term started on or
                           after this year (e.g. 2017 = last two mandates).
                           People with no recorded start date are always included.
        """
        date_filter = (
            f'FILTER(!BOUND(?startDate) || ?startDate >= "{since_year}-01-01"^^xsd:dateTime)'
            if since_year else ""
        )
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?startDate ?endDate ?description
        WHERE {{
          ?person p:P39 ?stmt .
          ?stmt ps:P39 wd:{position_qid} .
          OPTIONAL {{ ?stmt pq:P580 ?startDate }}
          OPTIONAL {{ ?stmt pq:P582 ?endDate }}
          {date_filter}
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

            start = self._date(self._val(b, "startDate"))
            end = self._date(self._val(b, "endDate"))
            # Avoid duplicate role entries for the same term
            existing = {(r.start_date, r.institution) for r in politicians[wid].roles}
            if (start, institution) not in existing:
                politicians[wid].roles.append(
                    PoliticianRole(
                        role=role_name,
                        institution=institution,
                        start_date=start,
                        end_date=end,
                    )
                )

        time.sleep(_SLEEP)
        return list(politicians.values())

    def fetch_federal_deputies(self, limit: int = 600, since_year: int = 2019) -> list[Politician]:
        """
        Fetch Brazilian Federal Deputies.
        Defaults to since_year=2019 (last two mandates: 56th + 57th legislatura).
        Pass since_year=None for all historical deputies.
        """
        seen: dict[str, Politician] = {}
        for qid in ("Q21609546", "Q23903549", "Q25028988"):
            results = self.fetch_politicians_by_position(
                qid, "Deputado Federal", "camara-deputados",
                ["câmara", "deputado-federal", "legislativo"],
                limit=limit, since_year=since_year,
            )
            for p in results:
                seen.setdefault(p.id, p)
            if seen:
                break
        if not seen:
            broad = self._fetch_politicians_by_occupation(
                extra_filter='?person wdt:P27 wd:Q155 .',
                role_name="Deputado Federal",
                institution="camara-deputados",
                tags=["câmara", "deputado-federal", "legislativo"],
                limit=limit,
            )
            for p in broad:
                seen.setdefault(p.id, p)
        return list(seen.values())

    def fetch_senators(self, limit: int = 300, since_year: int = 2019) -> list[Politician]:
        """
        Fetch Brazilian Senators.
        Defaults to since_year=2019 (last two election cycles).
        Pass since_year=None for all historical senators.
        """
        seen: dict[str, Politician] = {}
        for qid in ("Q18611017", "Q23903561", "Q25028990"):
            results = self.fetch_politicians_by_position(
                qid, "Senador Federal", "senado-federal",
                ["senado", "senador", "legislativo"],
                limit=limit, since_year=since_year,
            )
            for p in results:
                seen.setdefault(p.id, p)
            if seen:
                break
        if not seen:
            broad = self._fetch_politicians_by_occupation(
                extra_filter='?person wdt:P27 wd:Q155 .',
                role_name="Senador Federal",
                institution="senado-federal",
                tags=["senado", "senador", "legislativo"],
                limit=limit,
            )
            for p in broad:
                seen.setdefault(p.id, p)
        return list(seen.values())

    def fetch_presidents(self) -> list[Politician]:
        """Fetch all Presidents of Brazil (all time)."""
        seen: dict[str, Politician] = {}
        for qid in ("Q35137", "Q2801132", "Q148863"):
            results = self.fetch_politicians_by_position(
                qid, "Presidente da República", "presidencia-da-republica",
                ["presidente", "executivo"], limit=50,
            )
            for p in results:
                seen.setdefault(p.id, p)
            if seen:
                break
        # Fallback: description-based
        if not seen:
            logger.info("Presidents QID returned 0 — using description fallback")
            fallback = self._fetch_by_description_filter(
                filter_regex="presidente.*república|presidente.*brasil",
                role_name="Presidente da República",
                institution="presidencia-da-republica",
                tags=["presidente", "executivo"],
                limit=60,
            )
            for p in fallback:
                seen.setdefault(p.id, p)
        return list(seen.values())

    def fetch_governors(self, limit: int = 300, since_year: Optional[int] = None) -> list[Politician]:
        """
        Fetch Brazilian state governors.

        Uses a UNION of P31/P279 property paths so we catch all 27 state-specific
        Wikidata governor positions (e.g. "Governador de São Paulo" Q7546782), not
        just the generic Q5055441 which very few entries use directly.

        No date filter by default — Wikidata rarely records P580 for governors.
        Pass since_year to restrict (unreliable unless data is complete).
        """
        date_filter = (
            f'FILTER(!BOUND(?startDate) || ?startDate >= "{since_year}-01-01"^^xsd:dateTime)'
            if since_year else ""
        )
        # Match any P39 position whose Portuguese label contains "governador"
        # (covers all 27 state-specific positions like "Governador do Estado de SP"
        # as well as the generic Q5055441 — avoids QID guessing entirely).
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?startDate ?endDate ?description
        WHERE {{
          ?person wdt:P27 wd:Q155 ;
                  p:P39 ?stmt .
          ?stmt ps:P39 ?position .
          ?position rdfs:label ?posLabel .
          FILTER(LANG(?posLabel) = "pt" && REGEX(?posLabel, "governador", "i"))
          OPTIONAL {{ ?stmt pq:P580 ?startDate }}
          OPTIONAL {{ ?stmt pq:P582 ?endDate }}
          {date_filter}
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
                    tags=["governador", "executivo-estadual"],
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )
            start = self._date(self._val(b, "startDate"))
            end = self._date(self._val(b, "endDate"))
            existing = {(r.start_date, r.institution) for r in politicians[wid].roles}
            if (start, "governo-estadual") not in existing:
                politicians[wid].roles.append(
                    PoliticianRole(
                        role="Governador",
                        institution="governo-estadual",
                        start_date=start,
                        end_date=end,
                    )
                )

        time.sleep(_SLEEP)
        return list(politicians.values())

    def _fetch_politicians_by_occupation(
        self,
        extra_filter: str = "",
        role_name: str = "Político",
        institution: str = "brasil",
        tags: list[str] | None = None,
        limit: int = 2000,
    ) -> list[Politician]:
        """
        Fetch Brazilian politicians by occupation (Q82955) — no position QID needed.
        More robust fallback when position QIDs fail.
        """
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?description
        WHERE {{
          ?person wdt:P27 wd:Q155 ;
                  wdt:P106 wd:Q82955 .
          {extra_filter}
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
            name_label = self._val(b, "personLabel") or ""
            if self._is_qid(name_label):
                continue
            if wid not in politicians:
                politicians[wid] = Politician(
                    wikidata_id=wid,
                    name=name_label,
                    birth_date=self._date(self._val(b, "birthDate")),
                    birth_place=self._val(b, "birthPlaceLabel"),
                    party=self._val(b, "partyLabel"),
                    roles=[
                        PoliticianRole(
                            role=role_name,
                            institution=institution,
                        )
                    ],
                    tags=list(tags or []),
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )
        time.sleep(_SLEEP)
        return list(politicians.values())

    def _fetch_by_description_filter(
        self,
        filter_regex: str,
        role_name: str,
        institution: str,
        tags: list[str],
        limit: int = 200,
    ) -> list[Politician]:
        """
        Fallback fetcher: find Brazilian politicians by Portuguese description regex.
        Used when position QIDs are ambiguous or missing start-date data.
        """
        sparql = f"""
        SELECT DISTINCT ?person ?personLabel ?birthDate ?birthPlaceLabel
                        ?partyLabel ?description
        WHERE {{
          ?person wdt:P27 wd:Q155 .
          ?person schema:description ?description .
          FILTER(LANG(?description) = "pt" && REGEX(?description, "{filter_regex}", "i"))
          OPTIONAL {{ ?person wdt:P569 ?birthDate }}
          OPTIONAL {{ ?person wdt:P19 ?birthPlace }}
          OPTIONAL {{ ?person wdt:P102 ?party }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en" }}
        }}
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
                    roles=[PoliticianRole(role=role_name, institution=institution)],
                    tags=list(tags),
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                    summary=self._val(b, "description"),
                )
        time.sleep(_SLEEP)
        return list(politicians.values())

    def fetch_politicians_broad(self, limit: int = 2000) -> list[Politician]:
        """
        Fetch all Brazilian politicians by occupation (no position filter).
        Returns the broadest possible set — good for initial seeding.
        """
        return self._fetch_politicians_by_occupation(
            role_name="Político",
            institution="brasil",
            tags=["político", "brasil"],
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

    # ------------------------------------------------------------------
    # Historical events — sub-query helpers
    # ------------------------------------------------------------------

    def _event_query(
        self,
        type_values: str,
        seen: set[str],
        event_type: str = "event",
        limit: int = 2000,
    ) -> list[HistoricalEvent]:
        """Run one SPARQL event sub-query and return deduplicated HistoricalEvent objects."""
        sparql = f"""
        SELECT DISTINCT ?event ?eventLabel ?date ?endDate ?description
        WHERE {{
          ?event wdt:P17 wd:Q155 .
          ?event wdt:P31 ?type .
          VALUES ?type {{ {type_values} }}
          OPTIONAL {{ ?event wdt:P585 ?date }}
          OPTIONAL {{ ?event wdt:P582 ?endDate }}
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
        results: list[HistoricalEvent] = []
        for b in bindings:
            wid = self._wid(self._val(b, "event") or "")
            if not wid or wid in seen:
                continue
            seen.add(wid)
            title = self._val(b, "eventLabel") or ""
            if self._is_qid(title):
                continue
            results.append(
                HistoricalEvent(
                    wikidata_id=wid,
                    title=title,
                    date=self._date(self._val(b, "date")),
                    end_date=self._date(self._val(b, "endDate")),
                    type=event_type,
                    summary=self._val(b, "description") or "",
                    sources=[f"https://www.wikidata.org/wiki/{wid}"],
                )
            )
        time.sleep(_SLEEP)
        return results

    def fetch_political_events(self, limit: int = 2000) -> list[HistoricalEvent]:
        """
        Fetch major Brazilian political events from Wikidata.

        Runs 4 focused sub-queries to maximise coverage:
          1. Scandals / crises / investigations / operations
          2. Elections (all levels — federal, state, municipal)
          3. Social movements, protests, strikes
          4. Legislation, referendums, constitutional amendments

        No API key required. Default limit applies per sub-query.
        """
        seen: set[str] = set()
        all_events: list[HistoricalEvent] = []

        sub_limit = min(limit, 2000)

        # 1 — Scandals, crises, police operations, investigations
        all_events += self._event_query(
            "wd:Q2334719 wd:Q3307126 wd:Q1358461 wd:Q2101636 wd:Q16943273 wd:Q162875",
            seen, event_type="scandal", limit=sub_limit,
        )
        logger.info("Events after scandals/crises: %d", len(all_events))

        # 2 — Elections (all types)
        all_events += self._event_query(
            "wd:Q40231 wd:Q189760 wd:Q15275719 wd:Q1076105 wd:Q3544124",
            seen, event_type="election", limit=sub_limit,
        )
        logger.info("Events after elections: %d", len(all_events))

        # 3 — Social movements, protests, strikes
        all_events += self._event_query(
            "wd:Q1371582 wd:Q49773 wd:Q273120 wd:Q114953 wd:Q175331 wd:Q2726259",
            seen, event_type="movement", limit=sub_limit,
        )
        logger.info("Events after movements/protests: %d", len(all_events))

        # 4 — Legislation, constitutional events, coups
        all_events += self._event_query(
            "wd:Q3387717 wd:Q93288 wd:Q131569 wd:Q7283 wd:Q180684",
            seen, event_type="legislation", limit=sub_limit,
        )
        logger.info("Events after legislation/other: %d", len(all_events))

        return all_events

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
