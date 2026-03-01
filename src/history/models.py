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
    cpf: Optional[str] = None            # Brazilian CPF (11 digits, from TSE)
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


class CabinetStaff(BaseModel):
    """A staff member (secretário parlamentar) employed in a deputy's cabinet."""

    id: str = ""
    deputy_camara_id: int                # Câmara deputy numeric ID
    deputy_name: str                     # deputy's parlamentar name
    staff_name: str                      # full name of the staff member
    staff_cpf: Optional[str] = None      # CPF (11 digits, may be absent/masked)
    role: str = ""                       # CHEFE_DE_GABINETE | SECRETARIO_PARLAMENTAR | ASSESSOR_PARLAMENTAR | etc.
    start_date: Optional[str] = None     # YYYY-MM-DD (appointment date from source)
    end_date: Optional[str] = None       # None = active at time of snapshot
    legislature: int = 0                 # 56, 57, ...
    snapshot_month: str = ""             # YYYY-MM — month this snapshot was taken
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            # snapshot_month is part of the key so each periodic run creates new rows
            key = f"{self.deputy_camara_id}:{self.staff_cpf or self.staff_name}:{self.start_date or ''}:{self.snapshot_month}"
            self.id = "staff:" + hashlib.sha1(key.encode()).hexdigest()[:12]


class Legislature(BaseModel):
    """Metadata about a Brazilian legislative term (legislatura)."""

    id: int                          # 57, 56, 55, ...
    start_date: str                  # YYYY-MM-DD
    end_date: Optional[str] = None
    description: str = ""
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class CompanyProfile(BaseModel):
    """
    A Brazilian company enriched from Receita Federal / BrasilAPI.

    Primary key: cnpj (14 digits, no separators).
    socios stores the QSA (Quadro Societário e Administrativo) as returned by
    BrasilAPI — each entry has 'nome', 'cpf_cnpj_socio', 'qualificacao_socio'.
    Note: BrasilAPI may return partially masked CPFs (***111***-**).
    Full-CPF cross-references require the RF bulk dump.
    """

    cnpj: str                             # 14-digit string, primary key
    razao_social: str = ""                # legal name
    nome_fantasia: Optional[str] = None   # trade name
    situacao_cadastral: Optional[str] = None  # ATIVA | INAPTA | BAIXADA | SUSPENSA
    data_abertura: Optional[str] = None   # YYYY-MM-DD
    atividade_principal: Optional[str] = None  # JSON string: [{codigo, descricao}]
    municipio: Optional[str] = None
    uf: Optional[str] = None
    capital_social: Optional[float] = None
    socios: Optional[str] = None          # JSON string: [{nome, cpf_cnpj_socio, qualificacao_socio}]
    # Computed anti-corruption flags (set by lookup_cnpj.py)
    flags: list[str] = Field(default_factory=list)
    # Deputies who paid this CNPJ (set by lookup_cnpj.py for quick reference)
    paid_by_deputies: list[str] = Field(default_factory=list)  # ["camara:12345", ...]
    total_received_ceap: float = 0.0      # total R$ received via CEAP
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class NewsItem(BaseModel):
    """
    A news article ingested from an RSS feed or other source.

    id: URL-hash so the same article is never duplicated.
    politician_mentions: list of politician IDs matched from the article text.
    """

    id: str = ""
    url: str
    title: str
    summary: str = ""
    published_at: Optional[str] = None   # ISO datetime string
    source: str = ""                      # feed name, e.g. "agencia_brasil"
    source_url: str = ""                  # feed URL
    politician_mentions: list[str] = Field(default_factory=list)  # politician IDs
    fetched_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = "news:" + hashlib.sha1(self.url.encode()).hexdigest()[:12]
