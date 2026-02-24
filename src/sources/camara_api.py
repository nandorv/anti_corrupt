"""
Câmara dos Deputados REST API client.

Official API docs: https://dadosabertos.camara.leg.br/swagger/api.html

All requests go through the APICache layer — if the data is fresh in cache,
no network call is made. If the API is unreachable and cache is stale, the
stale value is returned with a warning (offline mode).

Endpoints used:
  GET /deputados                  → list all deputies
  GET /deputados/{id}             → single deputy detail
  GET /deputados/{id}/votacoes    → voting history for a deputy
  GET /votacoes/{id}              → voting session detail
  GET /proposicoes                → list propositions (filtered)
  GET /proposicoes/{id}           → single proposition detail
  GET /partidos                   → list parties
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.sources.cache import APICache, DEFAULT_TTL, get_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
_SOURCE = "camara"
_TIMEOUT = 15.0  # seconds


class CamaraAPIError(Exception):
    """Raised when the Câmara API returns an error and no cached fallback exists."""


class CamaraAPI:
    """
    Client for the Câmara dos Deputados open data API.

    All methods accept a `force_refresh` parameter. If True, the cache is
    bypassed and data is fetched live (useful for manual refresh commands).
    """

    def __init__(self, cache: Optional[APICache] = None, timeout: float = _TIMEOUT):
        self._cache = cache or get_cache()
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_key(self, endpoint: str, params: Optional[dict] = None) -> str:
        key = f"camara:{endpoint}"
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key = f"{key}?{param_str}"
        return key

    def _source_name(self, endpoint: str) -> str:
        """Map endpoint prefix to a source key for TTL lookup."""
        if "deputados" in endpoint:
            return "camara_deputados"
        if "votacoes" in endpoint or "votacoes" in endpoint:
            return "camara_votos"
        if "proposicoes" in endpoint:
            return "camara_proposicoes"
        return _SOURCE

    def _fetch(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        force_refresh: bool = False,
    ) -> Any:
        """
        Fetch data with cache-first strategy.

        1. Check cache → if fresh, return immediately.
        2. Try live API → store in cache → return.
        3. If API fails → return stale cache with warning.
        4. If API fails and no cache → raise CamaraAPIError.
        """
        key = self._cache_key(endpoint, params)
        source = self._source_name(endpoint)
        ttl = DEFAULT_TTL.get(source, DEFAULT_TTL["default"])

        # Step 1: Check cache
        if not force_refresh:
            entry = self._cache.get(key)
            if entry and entry.is_fresh(ttl):
                logger.debug("Cache HIT (fresh): %s", key)
                return entry.data

        # Step 2: Fetch from API
        try:
            response = self._client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            # Câmara API wraps responses in {"dados": [...], "links": [...]}
            payload = data.get("dados", data)
            self._cache.set(key, payload, source=source)
            logger.debug("Fetched and cached: %s", key)
            return payload

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # Step 3: Offline fallback — return stale cache if available
            stale = self._cache.get(key)
            if stale:
                age_h = stale.age_seconds / 3600
                logger.warning(
                    "Câmara API unreachable (%s). Using stale cache (%.1fh old): %s",
                    exc,
                    age_h,
                    key,
                )
                return stale.data
            # Step 4: No cache at all → fail
            raise CamaraAPIError(
                f"Câmara API request failed and no cached data available: {endpoint}"
            ) from exc

    # ------------------------------------------------------------------
    # Deputies
    # ------------------------------------------------------------------

    def list_deputies(
        self,
        legislature: Optional[int] = None,
        party: Optional[str] = None,
        state: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        List all deputies, optionally filtered by legislature, party, or state.
        Default legislature is the current one (57th).
        """
        params: dict = {"itens": 100, "ordem": "ASC", "ordenarPor": "nome"}
        if legislature:
            params["idLegislatura"] = legislature
        if party:
            params["siglaPartido"] = party
        if state:
            params["siglaUf"] = state

        results = []
        page = 1
        while True:
            params["pagina"] = page
            page_data = self._fetch("/deputados", params=dict(params), force_refresh=force_refresh)
            if not page_data:
                break
            # page_data can be a list (from "dados" extraction)
            if isinstance(page_data, list):
                results.extend(page_data)
                if len(page_data) < 100:
                    break
            else:
                break
            page += 1

        return results

    def get_deputy(self, deputy_id: int, force_refresh: bool = False) -> dict:
        """Get full detail for a single deputy."""
        data = self._fetch(f"/deputados/{deputy_id}", force_refresh=force_refresh)
        # Detail endpoint wraps in another level: {"dados": {...}}
        if isinstance(data, dict) and "id" not in data and len(data) == 1:
            return next(iter(data.values()))
        return data

    def get_deputy_votes(
        self,
        deputy_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """Get voting history for a deputy (dataInicio/dataFim as YYYY-MM-DD)."""
        params: dict = {"itens": 200, "ordem": "DESC", "ordenarPor": "dataHoraVoto"}
        if start_date:
            params["dataInicio"] = start_date
        if end_date:
            params["dataFim"] = end_date
        return self._fetch(
            f"/deputados/{deputy_id}/votacoes",
            params=params,
            force_refresh=force_refresh,
        ) or []

    # ------------------------------------------------------------------
    # Voting sessions
    # ------------------------------------------------------------------

    def get_vote_session(self, vote_id: str, force_refresh: bool = False) -> dict:
        """Get details of a specific voting session."""
        return self._fetch(f"/votacoes/{vote_id}", force_refresh=force_refresh) or {}

    def list_vote_sessions(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """List recent voting sessions."""
        params: dict = {"itens": 100, "ordem": "DESC", "ordenarPor": "dataHoraVoto"}
        if start_date:
            params["dataInicio"] = start_date
        if end_date:
            params["dataFim"] = end_date
        return self._fetch("/votacoes", params=params, force_refresh=force_refresh) or []

    # ------------------------------------------------------------------
    # Propositions (bills)
    # ------------------------------------------------------------------

    def list_propositions(
        self,
        keywords: Optional[str] = None,
        prop_type: Optional[str] = None,
        year: Optional[int] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        List propositions (bills, amendments, etc.).
        prop_type examples: PEC, PL, MP, PDL
        """
        params: dict = {"itens": 100, "ordem": "DESC", "ordenarPor": "ano"}
        if keywords:
            params["keywords"] = keywords
        if prop_type:
            params["siglaTipo"] = prop_type
        if year:
            params["ano"] = year
        return self._fetch("/proposicoes", params=params, force_refresh=force_refresh) or []

    def get_proposition(self, prop_id: int, force_refresh: bool = False) -> dict:
        """Get details of a specific proposition."""
        return self._fetch(f"/proposicoes/{prop_id}", force_refresh=force_refresh) or {}

    # ------------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------------

    def list_parties(
        self,
        legislature: Optional[int] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """List all registered parties."""
        params: dict = {"itens": 100, "ordem": "ASC", "ordenarPor": "sigla"}
        if legislature:
            params["idLegislatura"] = legislature
        return self._fetch("/partidos", params=params, force_refresh=force_refresh) or []

    # ------------------------------------------------------------------
    # Legislatures
    # ------------------------------------------------------------------

    def list_legislatures(self, force_refresh: bool = False) -> list[dict]:
        """
        List all legislative terms (legislaturas).

        Each record contains: id, dataInicio, dataFim, and uri.
        The current legislature is the one with no dataFim.
        """
        params: dict = {"itens": 100, "ordem": "DESC", "ordenarPor": "id"}
        return self._fetch("/legislaturas", params=params, force_refresh=force_refresh) or []

    # ------------------------------------------------------------------
    # CEAP Expenses
    # ------------------------------------------------------------------

    def get_deputy_expenses(
        self,
        deputy_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Get CEAP (Cota para o Exercício da Atividade Parlamentar) expense records
        for a deputy.

        Args:
            deputy_id: Numeric Câmara deputy ID
            year:      Filter by year (e.g. 2023)
            month:     Filter by month (1–12)

        Returns a list of expense dicts with fields including:
          ano, mes, tipoDespesa, nomeFornecedor, cnpjCpfFornecedor,
          valorDocumento, valorLiquido, numDocumento, urlDocumento
        """
        params: dict = {"itens": 200, "ordem": "DESC", "ordenarPor": "ano"}
        if year:
            params["ano"] = year
        if month:
            params["mes"] = month

        results = []
        page = 1
        while True:
            params["pagina"] = page
            page_data = self._fetch(
                f"/deputados/{deputy_id}/despesas",
                params=dict(params),
                force_refresh=force_refresh,
            )
            if not page_data:
                break
            if isinstance(page_data, list):
                results.extend(page_data)
                if len(page_data) < 200:
                    break
            else:
                break
            page += 1

        return results

    # ------------------------------------------------------------------
    # Voting session individual votes
    # ------------------------------------------------------------------

    def get_session_votes(
        self, session_id: str, force_refresh: bool = False
    ) -> list[dict]:
        """
        Get individual deputy votes within a specific voting session.

        Returns a list of vote dicts with fields:
          tipoVoto, dataRegistroVoto, deputado_ (sub-object with id, nome,
          siglaPartido, siglaUf, idLegislatura, urlFoto)
        """
        return (
            self._fetch(
                f"/votacoes/{session_id}/votos",
                force_refresh=force_refresh,
            )
            or []
        )

    # ------------------------------------------------------------------
    # Bulk refresh
    # ------------------------------------------------------------------

    def refresh_all(self) -> dict[str, int]:
        """
        Force-refresh all major data sets from the live API.
        Returns a dict of {endpoint: record_count}.
        """
        results: dict[str, int] = {}

        deputies = self.list_deputies(force_refresh=True)
        results["deputados"] = len(deputies)
        logger.info("Refreshed %d deputies", len(deputies))

        parties = self.list_parties(force_refresh=True)
        results["partidos"] = len(parties)
        logger.info("Refreshed %d parties", len(parties))

        return results

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CamaraAPI":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
