"""
Senado Federal open data API client.

API docs: https://legis.senado.leg.br/dadosabertos/docs/

Key endpoints used:
  GET /senador/lista/atual.json   → all senators currently in exercise
  GET /senador/{codigo}/resumo    → single senator detail

No authentication required. Returns JSON.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.history.models import Politician, PoliticianRole

logger = logging.getLogger(__name__)

BASE_URL = "https://legis.senado.leg.br/dadosabertos"
_TIMEOUT = 30.0


class SenadoAPIError(Exception):
    """Raised when the Senado API returns an error."""


class SenadoAPI:
    """
    Client for the Senado Federal open data API.

    Returns data about senators currently in exercise. The main endpoint
    (``/senador/lista/atual``) provides the exact real-time list of who
    is in office, including senators on leave and their substitutes.
    """

    def __init__(self, timeout: float = _TIMEOUT):
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_current_senators(self) -> list[Politician]:
        """
        Fetch all senators currently in exercise.

        Calls ``GET /senador/lista/atual.json`` — a single request that
        returns every senator who holds an active mandate right now,
        including those on leave (``IdentificacaoParlamentar``).

        Returns:
            ~81 Politician objects for the current Senate.
        """
        try:
            response = self._client.get("/senador/lista/atual.json")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise SenadoAPIError(f"Senado API request failed: {exc}") from exc

        # Navigate nested JSON structure
        try:
            parlamentares = (
                data["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
            )
        except (KeyError, TypeError) as exc:
            raise SenadoAPIError(
                f"Unexpected Senado API response structure: {exc}"
            ) from exc

        if not isinstance(parlamentares, list):
            parlamentares = [parlamentares]  # single-senator edge case

        politicians: list[Politician] = []
        for p in parlamentares:
            ident = p.get("IdentificacaoParlamentar", {})
            mandato = p.get("Mandato", {})

            codigo = ident.get("CodigoParlamentar", "")
            name = ident.get("NomeParlamentar") or ident.get(
                "NomeCompletoParlamentar", ""
            )
            party = ident.get("SiglaPartidoParlamentar") or None
            state = ident.get("UfParlamentar") or None

            if not name:
                continue

            # Mandate date range — senator has two consecutive legislatures
            leg1 = mandato.get("PrimeiraLegislaturaDoMandato") or {}
            leg2 = mandato.get("SegundaLegislaturaDoMandato") or {}
            start_date: Optional[str] = leg1.get("DataInicio")
            end_date: Optional[str] = (
                leg2.get("DataFim") or leg1.get("DataFim")
            )

            page_url = ident.get("UrlPaginaParlamentar") or (
                f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{codigo}"
            )

            politicians.append(
                Politician(
                    name=name,
                    party=party,
                    state=state,
                    tse_id=codigo,           # Senado CodigoParlamentar stored here
                    roles=[
                        PoliticianRole(
                            role="Senador",
                            institution="senado",
                            start_date=start_date,
                            end_date=end_date,
                        )
                    ],
                    tags=["senado", "senador", "legislativo"],
                    sources=[page_url],
                )
            )

        logger.info(
            "Senado API: fetched %d senators currently in exercise", len(politicians)
        )
        return politicians

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SenadoAPI":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()
