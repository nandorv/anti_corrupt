"""
Generic CSV importer for flat politician lists.

Expected input format (comma-separated, UTF-8 or Latin-1):
    nome, sede, tribunal, cargo

Where:
  nome      — full name
  sede      — city/state where they serve (e.g. "Brasília/DF", "São Paulo/SP")
  tribunal  — institution identifier (STF, STJ, TRF1, Executivo Federal, etc.)
  cargo     — role within the institution (may be empty)

This is the standard format for future manual imports. Place CSV files in
eleicoes/ and call CSVImporter.load(path) to get Politician objects.

Mapping files:
  TRIBUNAL_TO_INSTITUTION — maps tribunal name → institution slug used in PoliticianRole
  TRIBUNAL_TO_TAG         — maps tribunal name → short tag for search/filter
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from src.history.models import Politician, PoliticianRole

logger = logging.getLogger(__name__)

# ── Tribunal → institution slug ───────────────────────────────────────────────
TRIBUNAL_TO_INSTITUTION: dict[str, str] = {
    # Supreme / superior courts
    "STF":               "supremo_tribunal_federal",
    "STJ":               "superior_tribunal_justica",
    "TSE":               "tribunal_superior_eleitoral",
    "TST":               "tribunal_superior_trabalho",
    "STM":               "superior_tribunal_militar",
    "TCU":               "tribunal_contas_uniao",
    # Federal regional courts
    "TRF1":              "trf1",
    "TRF2":              "trf2",
    "TRF3":              "trf3",
    "TRF4":              "trf4",
    "TRF5":              "trf5",
    "TRF6":              "trf6",
    # Executive
    "Executivo Federal": "governo_federal",
    # Legislative
    "Câmara dos Deputados": "camara_dos_deputados",
    "Senado Federal":       "senado_federal",
    "Congresso Nacional":   "congresso_nacional",
}

# ── Tribunal → tag ────────────────────────────────────────────────────────────
TRIBUNAL_TO_TAG: dict[str, str] = {
    "STF":               "stf",
    "STJ":               "stj",
    "TSE":               "tse",
    "TST":               "tst",
    "STM":               "stm",
    "TCU":               "tcu",
    "TRF1":              "trf1",
    "TRF2":              "trf2",
    "TRF3":              "trf3",
    "TRF4":              "trf4",
    "TRF5":              "trf5",
    "TRF6":              "trf6",
    "Executivo Federal": "executivo_federal",
    "Câmara dos Deputados": "camara",
    "Senado Federal":       "senado",
}


def _parse_sede(sede: str) -> tuple[Optional[str], Optional[str]]:
    """'São Paulo/SP' → ('São Paulo', 'SP').  Falls back gracefully."""
    if "/" in sede:
        city, uf = sede.rsplit("/", 1)
        return city.strip(), uf.strip()
    return sede.strip() or None, None


class CSVImporter:
    """
    Loads a flat CSV with columns: nome, sede, tribunal, cargo
    and returns a list of Politician objects ready to upsert.

    Usage:
        from src.sources.csv_import import CSVImporter
        politicians = CSVImporter.load("eleicoes/magistrados_brasil.csv")
        store.upsert_politicians(politicians)
    """

    SOURCE_TAG = "csv_import"

    @classmethod
    def load(
        cls,
        path: str | Path,
        source_tag: Optional[str] = None,
        mandate_start: Optional[str] = None,
        mandate_end: Optional[str] = None,
    ) -> list[Politician]:
        """
        Parse a flat CSV and return Politician objects.

        Args:
            path:           Path to the CSV file.
            source_tag:     Override the source identifier (default: filename stem).
            mandate_start:  ISO date for role start_date (optional).
            mandate_end:    ISO date for role end_date (optional).
        """
        path = Path(path)
        tag = source_tag or f"csv:{path.stem}"
        politicians: list[Politician] = []
        skipped = 0

        # Detect encoding
        encoding = "utf-8"
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            encoding = "latin1"

        with open(path, encoding=encoding, errors="replace", newline="") as f:
            reader = csv.DictReader(f)

            # Normalise header names (strip whitespace/BOM)
            if reader.fieldnames:
                reader.fieldnames = [h.strip().lstrip("\ufeff") for h in reader.fieldnames]

            required = {"nome", "tribunal"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError(
                    f"CSV must have at least columns: {required}. "
                    f"Found: {reader.fieldnames}"
                )

            for row in reader:
                nome = (row.get("nome") or "").strip()
                if not nome:
                    skipped += 1
                    continue

                tribunal = (row.get("tribunal") or "").strip()
                cargo    = (row.get("cargo") or "").strip()
                sede     = (row.get("sede") or "").strip()

                city, uf = _parse_sede(sede)
                institution = TRIBUNAL_TO_INSTITUTION.get(tribunal, tribunal.lower().replace(" ", "_"))
                tag_short   = TRIBUNAL_TO_TAG.get(tribunal, tribunal.lower())

                role = PoliticianRole(
                    role=cargo or tribunal,
                    institution=institution,
                    start_date=mandate_start,
                    end_date=mandate_end,
                    notes=sede or None,
                )

                # ID: csv:<stem>:<normalised name>
                pol_id = f"csv:{path.stem}:{nome.lower().replace(' ', '_')}"

                COURT_TAGS = {"stf", "stj", "tse", "tst", "stm", "tcu", "trf1", "trf2", "trf3", "trf4", "trf5", "trf6"}
                extra_tags = ["magistrado"] if tag_short in COURT_TAGS else []

                politicians.append(Politician(
                    id=pol_id,
                    name=nome,
                    state=uf,
                    birth_place=city,
                    roles=[role],
                    tags=list({tag_short, *extra_tags}),
                    sources=[tag],
                ))

        if skipped:
            logger.warning("%s: skipped %d rows with empty name", path.name, skipped)

        logger.info("%s: loaded %d politicians from %s", cls.__name__, len(politicians), path.name)
        return politicians
