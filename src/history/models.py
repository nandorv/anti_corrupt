"""
Pydantic models for the historical database.

Record types:
  Politician      — person who held or holds public office
  HistoricalEvent — major events (scandals, elections, decisions, legislation)
  Vote            — individual deputy/senator vote on a proposition
  ElectionResult  — TSE electoral result per candidate
  Expense         — CEAP (deputies' discretionary expense) record
  Legislature     — metadata about a legislative term
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class PoliticianRole(BaseModel):
    """A single role held by a politician at an institution."""

    role: str
    institution: str
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Primary models
# ---------------------------------------------------------------------------


class Politician(BaseModel):
    """A Brazilian public figure who held or holds public office."""

    id: str = ""
    name: str
    birth_date: Optional[str] = None     # YYYY-MM-DD
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    education: list[str] = Field(default_factory=list)
    party: Optional[str] = None          # most recent / main party
    state: Optional[str] = None          # UF (SP, RJ, etc.)
    roles: list[PoliticianRole] = Field(default_factory=list)
    wikidata_id: Optional[str] = None    # e.g. "Q12345"
    camara_id: Optional[int] = None      # numeric ID from Câmara API
    tse_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            if self.wikidata_id:
                self.id = f"wikidata:{self.wikidata_id}"
            elif self.camara_id:
                self.id = f"camara:{self.camara_id}"
            else:
                self.id = f"pol:{uuid.uuid4().hex[:8]}"


class HistoricalEvent(BaseModel):
    """A major Brazilian political or institutional event."""

    id: str = ""
    title: str
    date: Optional[str] = None           # YYYY-MM-DD (start)
    end_date: Optional[str] = None
    type: str = "event"                  # scandal | legislation | election | decision | investigation | other
    summary: str = ""
    detailed_description: Optional[str] = None
    significance: Optional[str] = None
    actors: list[str] = Field(default_factory=list)        # politician IDs
    institutions: list[str] = Field(default_factory=list)  # institution slugs
    related_events: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    wikidata_id: Optional[str] = None
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            if self.wikidata_id:
                self.id = f"event:wikidata:{self.wikidata_id}"
            else:
                self.id = f"event:{uuid.uuid4().hex[:8]}"


class Vote(BaseModel):
    """An individual deputy's vote on a specific proposition (Câmara API)."""

    id: str = ""
    deputy_id: str = ""              # "camara:12345"
    deputy_camara_id: Optional[int] = None
    deputy_name: str
    proposition_id: str              # "camara:prop:12345"
    proposition_title: str = ""
    proposition_type: Optional[str] = None  # PEC, PL, MP, etc.
    vote: str                        # SIM | NÃO | ABSTENÇÃO | OBSTRUÇÃO | ARTIGO 17 | etc.
    date: str                        # YYYY-MM-DD
    session_id: Optional[str] = None
    party: Optional[str] = None
    state: Optional[str] = None
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if self.deputy_camara_id and not self.deputy_id:
            self.deputy_id = f"camara:{self.deputy_camara_id}"
        if not self.id:
            key = f"{self.deputy_id}:{self.proposition_id}:{self.date}:{self.session_id or ''}"
            self.id = "vote:" + hashlib.sha1(key.encode()).hexdigest()[:12]


class ElectionResult(BaseModel):
    """A candidate's result in a TSE election."""

    id: str = ""
    year: int
    state: str                       # UF sigla (SP, RJ, etc.) or "BR" for national
    municipality: Optional[str] = None
    position: str                    # PRESIDENTE, SENADOR, DEPUTADO FEDERAL, etc.
    candidate_name: str
    candidate_number: Optional[str] = None   # ballot number
    candidate_cpf: Optional[str] = None
    party: str
    coalition: Optional[str] = None
    votes: int = 0
    elected: bool = False
    round: int = 1                   # 1 or 2
    tse_seq_candidate: Optional[str] = None
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            key = f"{self.year}:{self.state}:{self.position}:{self.candidate_name}:{self.party}"
            self.id = "tse:" + hashlib.sha1(key.encode()).hexdigest()[:12]


class Expense(BaseModel):
    """A CEAP (Cota para o Exercício da Atividade Parlamentar) expense record."""

    id: str = ""
    deputy_id: str = ""              # "camara:12345"
    deputy_camara_id: Optional[int] = None
    deputy_name: str
    year: int
    month: int
    category: str                    # PASSAGENS AÉREAS, COMBUSTÍVEIS, etc.
    supplier: str
    supplier_cnpj_cpf: Optional[str] = None
    value: float
    document_number: Optional[str] = None
    description: Optional[str] = None
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if self.deputy_camara_id and not self.deputy_id:
            self.deputy_id = f"camara:{self.deputy_camara_id}"
        if not self.id:
            key = f"{self.deputy_id}:{self.year}:{self.month}:{self.category}:{self.supplier}:{self.value}:{self.document_number}"
            self.id = "ceap:" + hashlib.sha1(key.encode()).hexdigest()[:12]


class Legislature(BaseModel):
    """Metadata about a Brazilian legislative term (legislatura)."""

    id: int                          # 57, 56, 55, ...
    start_date: str                  # YYYY-MM-DD
    end_date: Optional[str] = None
    description: str = ""
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
