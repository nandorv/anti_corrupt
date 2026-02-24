"""Tests for knowledge base loader."""

import pytest
from pathlib import Path

from src.knowledge.loader import (
    load_events,
    load_figures,
    load_glossary,
    load_institutions,
    load_knowledge_base,
    load_relationships,
)
from src.knowledge.models import InstitutionType


class TestLoadInstitutions:
    def test_loads_all_institutions(self, data_dir: Path):
        institutions = load_institutions(data_dir)
        assert len(institutions) >= 5  # At least our 5 seeded institutions

    def test_stf_is_present(self, data_dir: Path):
        institutions = load_institutions(data_dir)
        assert "stf" in institutions

    def test_stf_is_judicial(self, data_dir: Path):
        institutions = load_institutions(data_dir)
        stf = institutions["stf"]
        assert stf.type == InstitutionType.JUDICIAL

    def test_schema_files_are_skipped(self, data_dir: Path):
        institutions = load_institutions(data_dir)
        # _schema.yaml should not be loaded as an institution
        assert "_schema" not in institutions

    def test_missing_directory_returns_empty(self, tmp_path: Path):
        institutions = load_institutions(tmp_path / "nonexistent")
        assert institutions == {}

    def test_congresso_has_children(self, data_dir: Path):
        institutions = load_institutions(data_dir)
        assert "congresso-nacional" in institutions
        congresso = institutions["congresso-nacional"]
        assert congresso.hierarchy is not None
        assert len(congresso.hierarchy.children) > 0


class TestLoadFigures:
    def test_loads_all_figures(self, data_dir: Path):
        figures = load_figures(data_dir)
        assert len(figures) >= 3  # lula, moraes, pacheco

    def test_lula_is_present(self, data_dir: Path):
        figures = load_figures(data_dir)
        assert "lula" in figures

    def test_lula_has_career(self, data_dir: Path):
        figures = load_figures(data_dir)
        lula = figures["lula"]
        assert len(lula.career) > 0

    def test_moraes_is_in_stf(self, data_dir: Path):
        figures = load_figures(data_dir)
        moraes = figures["alexandre-de-moraes"]
        stf_entries = [c for c in moraes.career if "stf" in c.institution.lower()]
        assert len(stf_entries) > 0


class TestLoadEvents:
    def test_loads_all_events(self, data_dir: Path):
        events = load_events(data_dir)
        assert len(events) >= 3

    def test_constituicao_is_present(self, data_dir: Path):
        events = load_events(data_dir)
        assert "constituicao-1988" in events

    def test_lava_jato_has_dates(self, data_dir: Path):
        events = load_events(data_dir)
        lj = events["operacao-lava-jato"]
        assert lj.date is not None
        assert lj.end_date is not None
        assert lj.end_date > lj.date


class TestLoadRelationships:
    def test_loads_relationships(self, data_dir: Path):
        relationships = load_relationships(data_dir)
        assert len(relationships) > 0

    def test_relationships_have_required_fields(self, data_dir: Path):
        relationships = load_relationships(data_dir)
        for rel in relationships:
            assert rel.id
            assert rel.source_id
            assert rel.target_id
            assert rel.description


class TestLoadGlossary:
    def test_loads_glossary_terms(self, data_dir: Path):
        glossary = load_glossary(data_dir)
        assert len(glossary) >= 5

    def test_impeachment_term_is_present(self, data_dir: Path):
        glossary = load_glossary(data_dir)
        assert "impeachment" in glossary

    def test_term_has_definition(self, data_dir: Path):
        glossary = load_glossary(data_dir)
        term = glossary["habeas-corpus"]
        assert term.definition
        assert len(term.definition) > 20


class TestLoadKnowledgeBase:
    def test_loads_full_kb(self, data_dir: Path):
        kb = load_knowledge_base(data_dir)
        assert kb.total_entities > 0
        assert len(kb.institutions) > 0
        assert len(kb.figures) > 0
        assert len(kb.events) > 0
        assert len(kb.relationships) > 0
        assert len(kb.glossary) > 0

    def test_kb_summary_keys(self, data_dir: Path):
        kb = load_knowledge_base(data_dir)
        s = kb.summary()
        assert all(k in s for k in [
            "institutions", "figures", "events", "relationships",
            "glossary_terms", "total_entities"
        ])
