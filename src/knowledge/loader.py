"""
Knowledge base YAML loader.
Reads all YAML files from the data directory and returns validated Pydantic models.
"""

from pathlib import Path
from typing import Any

import yaml

from .models import (
    Event,
    GlossaryTerm,
    Institution,
    KnowledgeBase,
    PublicFigure,
    Relationship,
)


def _load_yaml(path: Path) -> Any:
    """Load and parse a single YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_institutions(data_dir: Path) -> dict[str, Institution]:
    """Load all institution YAML files from data/institutions/."""
    institutions: dict[str, Institution] = {}
    inst_dir = data_dir / "institutions"
    if not inst_dir.exists():
        return institutions
    for path in sorted(inst_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _load_yaml(path)
        inst = Institution.model_validate(data)
        institutions[inst.id] = inst
    return institutions


def load_figures(data_dir: Path) -> dict[str, PublicFigure]:
    """Load all figure YAML files from data/figures/."""
    figures: dict[str, PublicFigure] = {}
    fig_dir = data_dir / "figures"
    if not fig_dir.exists():
        return figures
    for path in sorted(fig_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _load_yaml(path)
        fig = PublicFigure.model_validate(data)
        figures[fig.id] = fig
    return figures


def load_events(data_dir: Path) -> dict[str, Event]:
    """Load all event YAML files from data/events/."""
    events: dict[str, Event] = {}
    events_dir = data_dir / "events"
    if not events_dir.exists():
        return events
    for path in sorted(events_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _load_yaml(path)
        event = Event.model_validate(data)
        events[event.id] = event
    return events


def load_relationships(data_dir: Path) -> list[Relationship]:
    """
    Load all relationship YAML files from data/relationships/.
    Supports two formats:
      - A single relationship at the top level
      - A list under the key 'relationships:'
    """
    relationships: list[Relationship] = []
    rel_dir = data_dir / "relationships"
    if not rel_dir.exists():
        return relationships
    for path in sorted(rel_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _load_yaml(path)
        if isinstance(data, list):
            for item in data:
                relationships.append(Relationship.model_validate(item))
        elif isinstance(data, dict) and "relationships" in data:
            for item in data["relationships"]:
                relationships.append(Relationship.model_validate(item))
        else:
            relationships.append(Relationship.model_validate(data))
    return relationships


def load_glossary(data_dir: Path) -> dict[str, GlossaryTerm]:
    """
    Load all glossary YAML files from data/glossary/.
    Supports two formats:
      - A single term at the top level
      - A list under the key 'terms:'
    """
    glossary: dict[str, GlossaryTerm] = {}
    glossary_dir = data_dir / "glossary"
    if not glossary_dir.exists():
        return glossary
    for path in sorted(glossary_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _load_yaml(path)
        if isinstance(data, dict) and "terms" in data:
            terms_list = data["terms"]
        elif isinstance(data, list):
            terms_list = data
        else:
            terms_list = [data]
        for item in terms_list:
            term = GlossaryTerm.model_validate(item)
            glossary[term.id] = term
    return glossary


def load_knowledge_base(data_dir: Path) -> KnowledgeBase:
    """Load the complete knowledge base from a data directory."""
    return KnowledgeBase(
        institutions=load_institutions(data_dir),
        figures=load_figures(data_dir),
        events=load_events(data_dir),
        relationships=load_relationships(data_dir),
        glossary=load_glossary(data_dir),
    )
