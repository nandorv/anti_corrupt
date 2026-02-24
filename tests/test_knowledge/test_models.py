"""Tests for knowledge base Pydantic models."""

import pytest
import datetime as dt
from pydantic import ValidationError

from src.knowledge.models import (
    CareerEntry,
    Controversy,
    ControversyStatus,
    EntityType,
    Event,
    EventType,
    GlossaryTerm,
    HierarchyInfo,
    Institution,
    InstitutionType,
    KnowledgeBase,
    PublicFigure,
    Relationship,
    RelationshipStrength,
    RelationshipType,
)


# ── Institution ───────────────────────────────────────────────────────────────

class TestInstitution:
    def test_valid_institution(self):
        inst = Institution(
            id="stf",
            name_official="Supremo Tribunal Federal",
            name_common="STF",
            acronym="STF",
            type=InstitutionType.JUDICIAL,
            jurisdiction="Federal",
            description="O órgão de cúpula do Poder Judiciário.",
        )
        assert inst.id == "stf"
        assert inst.type == InstitutionType.JUDICIAL
        assert inst.key_functions == []
        assert inst.tags == []

    def test_institution_with_hierarchy(self):
        inst = Institution(
            id="senado-federal",
            name_official="Senado Federal",
            name_common="Senado",
            acronym="SF",
            type=InstitutionType.LEGISLATIVE,
            jurisdiction="Federal",
            description="A câmara alta do Congresso Nacional.",
            hierarchy=HierarchyInfo(parent="congresso-nacional", children=[]),
        )
        assert inst.hierarchy is not None
        assert inst.hierarchy.parent == "congresso-nacional"

    def test_invalid_institution_type(self):
        with pytest.raises(ValidationError):
            Institution(
                id="test",
                name_official="Test",
                name_common="Test",
                acronym="T",
                type="invalid_type",  # Invalid enum value
                jurisdiction="Federal",
                description="Test",
            )

    def test_institution_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Institution(
                id="test",
                # Missing: name_official, name_common, acronym, type, jurisdiction, description
            )


# ── PublicFigure ──────────────────────────────────────────────────────────────

class TestPublicFigure:
    def test_valid_figure(self):
        fig = PublicFigure(
            id="lula",
            full_name="Luiz Inácio Lula da Silva",
        )
        assert fig.id == "lula"
        assert fig.birth_date is None
        assert fig.career == []
        assert fig.current_role is None

    def test_figure_current_role(self):
        fig = PublicFigure(
            id="test-figure",
            full_name="Test Figure",
            career=[
                CareerEntry(
                    role="Cargo Anterior",
                    institution="org-a",
                    start_date=dt.date(2010, 1, 1),
                    end_date=dt.date(2020, 1, 1),
                ),
                CareerEntry(
                    role="Cargo Atual",
                    institution="org-b",
                    start_date=dt.date(2020, 1, 1),
                    end_date=None,  # Current
                ),
            ],
        )
        assert fig.current_role == "Cargo Atual"
        assert fig.current_institution == "org-b"

    def test_figure_with_controversy(self):
        fig = PublicFigure(
            id="test",
            full_name="Test Figure",
            controversies=[
                Controversy(
                    title="Test Controversy",
                    summary="A test controversy.",
                    status=ControversyStatus.ALLEGED,
                )
            ],
        )
        assert len(fig.controversies) == 1
        assert fig.controversies[0].status == ControversyStatus.ALLEGED

    def test_figure_invalid_controversy_status(self):
        with pytest.raises(ValidationError):
            PublicFigure(
                id="test",
                full_name="Test",
                controversies=[
                    {
                        "title": "Test",
                        "summary": "Test",
                        "status": "unknown_status",  # Invalid
                    }
                ],
            )


# ── Event ─────────────────────────────────────────────────────────────────────

class TestEvent:
    def test_valid_event(self):
        event = Event(
            id="constituicao-1988",
            title="Promulgação da Constituição Federal",
            date=dt.date(1988, 10, 5),
            type=EventType.LAW,
            summary="Promulgação da Constituição Cidadã.",
        )
        assert event.id == "constituicao-1988"
        assert event.date == dt.date(1988, 10, 5)
        assert event.actors == []
        assert event.causes == []

    def test_event_missing_date(self):
        with pytest.raises(ValidationError):
            Event(
                id="test",
                title="Test Event",
                # Missing: date (required)
                type=EventType.OTHER,
                summary="Test",
            )

    def test_event_with_actors_and_institutions(self):
        event = Event(
            id="test-event",
            title="Test",
            date=dt.date(2020, 1, 1),
            type=EventType.DECISION,
            summary="A test event.",
            actors=[{"figure_id": "some-figure", "role": "autor"}],
            institutions_involved=["stf", "senado-federal"],
        )
        assert len(event.actors) == 1
        assert len(event.institutions_involved) == 2


# ── Relationship ──────────────────────────────────────────────────────────────

class TestRelationship:
    def test_valid_relationship(self):
        rel = Relationship(
            id="test-rel",
            source_type=EntityType.FIGURE,
            source_id="lula",
            target_type=EntityType.INSTITUTION,
            target_id="presidencia-da-republica",
            relationship_type=RelationshipType.MEMBER_OF,
            description="Lula é presidente.",
            strength=RelationshipStrength.STRONG,
        )
        assert rel.id == "test-rel"
        assert rel.end_date is None  # ongoing

    def test_relationship_invalid_type(self):
        with pytest.raises(ValidationError):
            Relationship(
                id="bad",
                source_type="invalid_type",  # Invalid
                source_id="a",
                target_type=EntityType.INSTITUTION,
                target_id="b",
                relationship_type=RelationshipType.CHECKS,
                description="Test",
                strength=RelationshipStrength.WEAK,
            )


# ── GlossaryTerm ──────────────────────────────────────────────────────────────

class TestGlossaryTerm:
    def test_valid_term(self):
        term = GlossaryTerm(
            id="habeas-corpus",
            term_pt="Habeas Corpus",
            definition="Instrumento que protege a liberdade de locomoção.",
        )
        assert term.id == "habeas-corpus"
        assert term.term_en is None
        assert term.related_terms == []

    def test_term_missing_required(self):
        with pytest.raises(ValidationError):
            GlossaryTerm(
                id="test",
                # Missing: term_pt, definition
            )


# ── KnowledgeBase ─────────────────────────────────────────────────────────────

class TestKnowledgeBase:
    def test_empty_knowledge_base(self):
        kb = KnowledgeBase()
        assert kb.total_entities == 0
        assert kb.summary()["institutions"] == 0

    def test_knowledge_base_summary(self):
        kb = KnowledgeBase(
            institutions={
                "stf": Institution(
                    id="stf",
                    name_official="STF",
                    name_common="STF",
                    acronym="STF",
                    type=InstitutionType.JUDICIAL,
                    jurisdiction="Federal",
                    description="Test",
                )
            }
        )
        s = kb.summary()
        assert s["institutions"] == 1
        assert s["total_entities"] == 1
