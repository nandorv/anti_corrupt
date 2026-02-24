"""
Knowledge base Pydantic models.
Every entity in the system is validated through these models.
"""

import datetime as dt
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enumerations ─────────────────────────────────────────────────────────────

class InstitutionType(str, Enum):
    EXECUTIVE = "executive"
    LEGISLATIVE = "legislative"
    JUDICIAL = "judicial"
    INDEPENDENT = "independent"
    MILITARY = "military"
    OTHER = "other"


class EventType(str, Enum):
    LAW = "law"
    DECISION = "decision"
    CRISIS = "crisis"
    ELECTION = "election"
    APPOINTMENT = "appointment"
    SCANDAL = "scandal"
    REFORM = "reform"
    OTHER = "other"


class EntityType(str, Enum):
    FIGURE = "figure"
    INSTITUTION = "institution"
    EVENT = "event"


class RelationshipType(str, Enum):
    APPOINTED_BY = "appointed_by"
    MEMBER_OF = "member_of"
    RULED_ON = "ruled_on"
    ALLIED_WITH = "allied_with"
    OPPOSED = "opposed"
    INVESTIGATED = "investigated"
    FUNDED_BY = "funded_by"
    SUCCEEDED = "succeeded"
    OVERSEES = "oversees"
    CHECKS = "checks"
    CAUSED = "caused"
    LED_TO = "led_to"
    ACTOR_IN = "actor_in"
    PART_OF = "part_of"


class RelationshipStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class ControversyStatus(str, Enum):
    ALLEGED = "alleged"
    INVESTIGATED = "investigated"
    CHARGED = "charged"
    CONVICTED = "convicted"
    ACQUITTED = "acquitted"
    ONGOING = "ongoing"
    CLOSED = "closed"


# ── Sub-models ────────────────────────────────────────────────────────────────

class CompositionInfo(BaseModel):
    total_members: Optional[int] = None
    how_appointed: Optional[str] = None
    term_length: Optional[str] = None


class LeadershipEntry(BaseModel):
    name: str
    role: str
    since: Optional[dt.date] = None


class HierarchyInfo(BaseModel):
    parent: Optional[str] = None  # institution_id or null
    children: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str
    degree: str
    year: Optional[int] = None


class CareerEntry(BaseModel):
    role: str
    institution: str
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None  # None = current position
    description: Optional[str] = None


class PartyAffiliation(BaseModel):
    party: str
    start: Optional[dt.date] = None
    end: Optional[dt.date] = None  # None = current


class Controversy(BaseModel):
    title: str
    date: Optional[dt.date] = None
    summary: str
    sources: list[str] = Field(default_factory=list)
    status: ControversyStatus


class PublicPosition(BaseModel):
    topic: str
    position: str
    source: Optional[str] = None


class EventActor(BaseModel):
    figure_id: str
    role: str


# ── Primary Entity Models ─────────────────────────────────────────────────────

class Institution(BaseModel):
    id: str
    name_official: str
    name_common: str
    acronym: str
    type: InstitutionType
    jurisdiction: str
    established: Optional[dt.date] = None
    constitutional_basis: Optional[str] = None
    description: str
    key_functions: list[str] = Field(default_factory=list)
    composition: Optional[CompositionInfo] = None
    current_leadership: list[LeadershipEntry] = Field(default_factory=list)
    hierarchy: Optional[HierarchyInfo] = None
    related_institutions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    last_updated: Optional[dt.datetime] = None


class PublicFigure(BaseModel):
    id: str
    full_name: str
    birth_date: Optional[dt.date] = None
    birth_place: Optional[str] = None
    education: list[EducationEntry] = Field(default_factory=list)
    career: list[CareerEntry] = Field(default_factory=list)
    party_affiliations: list[PartyAffiliation] = Field(default_factory=list)
    key_decisions: list[str] = Field(default_factory=list)  # event IDs
    controversies: list[Controversy] = Field(default_factory=list)
    public_positions: list[PublicPosition] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    last_updated: Optional[dt.datetime] = None

    @property
    def current_role(self) -> Optional[str]:
        """Return the most recent position with no end date."""
        for entry in reversed(self.career):
            if entry.end_date is None:
                return entry.role
        return None

    @property
    def current_institution(self) -> Optional[str]:
        """Return the institution of the most recent active position."""
        for entry in reversed(self.career):
            if entry.end_date is None:
                return entry.institution
        return None


class Event(BaseModel):
    id: str
    title: str
    date: dt.date
    end_date: Optional[dt.date] = None
    type: EventType
    summary: str
    detailed_description: Optional[str] = None
    significance: Optional[str] = None
    actors: list[EventActor] = Field(default_factory=list)
    institutions_involved: list[str] = Field(default_factory=list)
    causes: list[str] = Field(default_factory=list)    # event IDs
    consequences: list[str] = Field(default_factory=list)  # event IDs
    timeline_group: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    last_updated: Optional[dt.datetime] = None


class Relationship(BaseModel):
    id: str
    source_type: EntityType
    source_id: str
    target_type: EntityType
    target_id: str
    relationship_type: RelationshipType
    description: str
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None  # None = ongoing
    strength: RelationshipStrength
    sources: list[str] = Field(default_factory=list)
    last_updated: Optional[dt.datetime] = None


class GlossaryTerm(BaseModel):
    id: str
    term_pt: str
    term_en: Optional[str] = None
    definition: str
    legal_definition: Optional[str] = None
    example: Optional[str] = None
    related_terms: list[str] = Field(default_factory=list)
    related_institutions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


# ── Knowledge Base Container ──────────────────────────────────────────────────

class KnowledgeBase(BaseModel):
    """Container for the fully loaded and validated knowledge base."""

    institutions: dict[str, Institution] = Field(default_factory=dict)
    figures: dict[str, PublicFigure] = Field(default_factory=dict)
    events: dict[str, Event] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    glossary: dict[str, GlossaryTerm] = Field(default_factory=dict)

    @property
    def total_entities(self) -> int:
        return (
            len(self.institutions)
            + len(self.figures)
            + len(self.events)
            + len(self.glossary)
        )

    def summary(self) -> dict[str, int]:
        return {
            "institutions": len(self.institutions),
            "figures": len(self.figures),
            "events": len(self.events),
            "relationships": len(self.relationships),
            "glossary_terms": len(self.glossary),
            "total_entities": self.total_entities,
        }
