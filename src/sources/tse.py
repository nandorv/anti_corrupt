"""
TSE (Tribunal Superior Eleitoral) open data client.

Data portal: https://dadosabertos.tse.jus.br/
CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/

Files downloaded as ZIP archives containing semicolon-delimited CSV files
encoded in Latin-1.

Available datasets:
  consulta_cand_{year}.zip   — candidate registrations per election year
                               includes election result status (elected/not)

Election years with data:
  1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008,
  2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024

Note: The full result files (votacao_candidato_munzona) are 100MB–1GB+.
      This client uses the lighter candidates file which already contains
      the "situação de totalização" (elected/not elected) field.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from pathlib import Path
from typing import Iterator, Optional

import httpx

from src.history.models import ElectionResult

logger = logging.getLogger(__name__)

_CDN_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
_TIMEOUT = 180.0  # large files — be generous

# All election years for which TSE has data
ELECTION_YEARS = [
    1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008,
    2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024,
]

# Normalise TSE position codes to short names
POSITION_MAP: dict[str, str] = {
    "PRESIDENTE DA REPÚBLICA": "PRESIDENTE",
    "VICE-PRESIDENTE DA REPÚBLICA": "VICE-PRESIDENTE",
    "GOVERNADOR": "GOVERNADOR",
    "VICE-GOVERNADOR": "VICE-GOVERNADOR",
    "SENADOR": "SENADOR",
    "DEPUTADO FEDERAL": "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL": "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL": "DEPUTADO DISTRITAL",
    "PREFEITO": "PREFEITO",
    "VICE-PREFEITO": "VICE-PREFEITO",
    "VEREADOR": "VEREADOR",
    "JUIZ DE PAZ": "JUIZ DE PAZ",
}

# TSE "elected" status codes that appear in DS_SIT_TOT_TURNO
_ELECTED_TERMS = {"ELEITO", "ELEITA", "ELEITO POR MÉDIA", "ELEITO POR QP", "ELEITA POR QP"}


class TSEError(Exception):
    """Raised when TSE data download or parsing fails."""


class TSEClient:
    """
    Client for TSE open electoral data.

    Downloads ZIP files from the TSE CDN, extracts CSVs in memory, and
    parses them into ElectionResult records.

    Args:
        timeout:   HTTP timeout in seconds (large files — use 120+)
        cache_dir: If set, downloaded ZIPs are saved here to avoid
                   re-downloading on subsequent calls.
    """

    def __init__(self, timeout: float = _TIMEOUT, cache_dir: Optional[Path] = None):
        self._timeout = timeout
        self._cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "AntiCorrupt/1.0 Python/httpx"},
        )

    # ------------------------------------------------------------------
    # Low-level download + parse
    # ------------------------------------------------------------------

    def _download(self, url: str, local_name: str) -> bytes:
        """Download a file, using cache_dir as a local disk cache if set."""
        if self._cache_dir:
            cached = self._cache_dir / local_name
            if cached.exists():
                logger.info("TSE cache hit: %s", cached)
                return cached.read_bytes()

        logger.info("Downloading TSE file: %s", url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TSEError(f"Download failed for {url}: {exc}") from exc

        content = response.content
        logger.info("Downloaded %.1f MB", len(content) / 1_048_576)

        if self._cache_dir:
            (self._cache_dir / local_name).write_bytes(content)

        return content

    def _iter_csv_rows(self, zip_bytes: bytes, encoding: str = "latin-1") -> Iterator[dict]:
        """
        Extract the largest CSV from a ZIP archive and yield each row as a dict.
        Handles both semicolon and comma delimiters (TSE uses semicolons).
        """
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_files:
                raise TSEError("No CSV files found in the downloaded ZIP archive.")
            # Pick the largest CSV — usually the main data file
            csv_name = max(csv_files, key=lambda n: zf.getinfo(n).file_size)
            logger.info("Parsing TSE CSV: %s", csv_name)
            with zf.open(csv_name) as f:
                text = f.read().decode(encoding, errors="replace")
                reader = csv.DictReader(io.StringIO(text), delimiter=";")
                yield from reader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_candidates(
        self,
        year: int,
        state: Optional[str] = None,
        position: Optional[str] = None,
        limit: int = 2000,
    ) -> list[ElectionResult]:
        """
        Download and parse candidate data for a given election year.

        This uses the `consulta_cand_{year}.zip` file which contains candidate
        registrations with their final election status (elected or not).

        Args:
            year:     Election year (must be in ELECTION_YEARS)
            state:    Filter by UF sigla (e.g. "SP"). None = all states.
            position: Filter by position substring (e.g. "DEPUTADO"). None = all.
            limit:    Maximum number of records to return.

        Returns:
            List of ElectionResult objects.
        """
        if year not in ELECTION_YEARS:
            raise TSEError(
                f"Year {year} not available. Choose from: {ELECTION_YEARS}"
            )

        url = f"{_CDN_BASE}/consulta_cand/consulta_cand_{year}.zip"
        zip_bytes = self._download(url, f"tse_cand_{year}.zip")

        results: list[ElectionResult] = []
        count = 0

        for row in self._iter_csv_rows(zip_bytes):
            if count >= limit:
                break

            # State filter — try multiple column name variants across years
            uf = (row.get("SG_UF") or row.get("UF_CANDIDATO") or "").strip().upper()
            if state and uf != state.upper():
                continue

            # Position
            pos_raw = (row.get("DS_CARGO") or row.get("NM_CARGO") or "").strip().upper()
            if position and position.upper() not in pos_raw:
                continue
            pos = POSITION_MAP.get(pos_raw, pos_raw)

            # Candidate name
            name = (
                row.get("NM_CANDIDATO")
                or row.get("NM_URNA_CANDIDATO")
                or ""
            ).strip()
            party = (row.get("SG_PARTIDO") or row.get("NM_PARTIDO") or "").strip()
            if not name or not party:
                continue

            # Election result status — use exact set membership to avoid
            # "NÃO ELEITO" matching "ELEITO" as a substring
            status_raw = (
                row.get("DS_SIT_TOT_TURNO")
                or row.get("CD_SIT_TOT_TURNO")
                or ""
            ).strip().upper()
            elected = status_raw in _ELECTED_TERMS

            # Optional fields
            number = (row.get("NR_CANDIDATO") or "").strip()
            cpf_raw = (row.get("NR_CPF_CANDIDATO") or "").strip()
            cpf = cpf_raw if len(cpf_raw) >= 11 else None
            seq = (row.get("SQ_CANDIDATO") or "").strip()

            try:
                result = ElectionResult(
                    year=year,
                    state=uf or (state or "BR"),
                    position=pos,
                    candidate_name=name,
                    candidate_number=number or None,
                    candidate_cpf=cpf,
                    party=party,
                    votes=0,          # vote counts require a separate (heavier) file
                    elected=elected,
                    round=1,
                    tse_seq_candidate=seq or None,
                )
                results.append(result)
                count += 1
            except Exception as exc:
                logger.debug("Skipping TSE row: %s — %s", row.get("NM_CANDIDATO"), exc)

        logger.info("Parsed %d candidates for year %d", len(results), year)
        return results

    def list_available_years(self) -> list[int]:
        """Return all election years for which TSE has open data."""
        return list(ELECTION_YEARS)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "TSEClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
