"""
AI explainer — generates educational content about Brazilian institutions,
public figures, events, and glossary concepts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.ai.client import BaseLLMClient, LLMResponse, get_client
from src.ai.prompts import get_prompt
from src.knowledge.models import Event, Institution, KnowledgeBase, PublicFigure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass
class ExplainerResult:
    """Structured explainer content."""

    entity_id: str
    entity_type: str  # institution | figure | event | concept
    raw_text: str
    # Parsed sections (populated for institution explainers)
    what_it_is: str = ""
    what_it_does: str = ""
    how_it_works: str = ""
    role_in_system: str = ""
    practical_example: str = ""
    response: Optional[LLMResponse] = None

    @classmethod
    def parse_institution(cls, entity_id: str, response: LLMResponse) -> "ExplainerResult":
        text = response.content
        obj = cls(
            entity_id=entity_id,
            entity_type="institution",
            raw_text=text,
            response=response,
        )
        sections = {
            "**O que é**": "what_it_is",
            "**Para que serve**": "what_it_does",
            "**Como funciona**": "how_it_works",
            "**Seu papel no sistema**": "role_in_system",
            "**Exemplo prático**": "practical_example",
        }
        _parse_sections(obj, text, sections)
        return obj


@dataclass
class ProfileResult:
    """Public figure profile content."""

    entity_id: str
    raw_text: str
    who_is: str = ""
    current_role: str = ""
    trajectory: str = ""
    relevance: str = ""
    controversies_summary: str = ""
    response: Optional[LLMResponse] = None

    @classmethod
    def parse(cls, entity_id: str, response: LLMResponse) -> "ProfileResult":
        text = response.content
        obj = cls(entity_id=entity_id, raw_text=text, response=response)
        sections = {
            "**Quem é**": "who_is",
            "**Formação e carreira**": "current_role",
            "**Principais decisões ou ações**": "trajectory",
            "**Controvérsias**": "controversies_summary",
            "**Posições públicas conhecidas**": "relevance",
        }
        _parse_sections(obj, text, sections)
        return obj


@dataclass
class TimelineResult:
    """Timeline narrative content."""

    timeline_group: str
    raw_text: str
    narrative: str = ""
    key_moments: list[str] = field(default_factory=list)
    lessons: str = ""
    response: Optional[LLMResponse] = None

    @classmethod
    def parse(cls, timeline_group: str, response: LLMResponse) -> "TimelineResult":
        text = response.content
        obj = cls(timeline_group=timeline_group, raw_text=text, response=response)
        sections = {
            "**Visão geral**": "narrative",
            "**Linha do tempo**": "key_moments",
            "**Consequências principais**": "lessons",
        }
        _parse_sections(obj, text, sections)
        return obj


# ---------------------------------------------------------------------------
# Section parser helper
# ---------------------------------------------------------------------------


def _parse_sections(obj: object, text: str, sections: dict[str, str]) -> None:
    lines = text.splitlines()
    current_key: Optional[str] = None
    buffer: list[str] = []

    for line in lines:
        stripped = line.strip()
        matched = False
        for header, attr in sections.items():
            if stripped.startswith(header):
                if current_key:
                    _apply_buffer(obj, current_key, buffer)
                current_key = attr
                buffer = []
                matched = True
                break
        if not matched and current_key:
            buffer.append(line)

    if current_key:
        _apply_buffer(obj, current_key, buffer)


def _apply_buffer(obj: object, key: str, buffer: list[str]) -> None:
    content = "\n".join(buffer).strip()
    if isinstance(getattr(obj, key, None), list):
        # Parse bullet list
        items = [
            line.lstrip("-•*").strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        setattr(obj, key, [i for i in items if i])
    else:
        setattr(obj, key, content)


# ---------------------------------------------------------------------------
# Explainer class
# ---------------------------------------------------------------------------


class ContentExplainer:
    """Generate educational content from knowledge base entities."""

    def __init__(self, kb: KnowledgeBase, client: Optional[BaseLLMClient] = None) -> None:
        self.kb = kb
        self.client = client or get_client()
        self._inst_prompt = get_prompt("explain_institution")
        self._profile_prompt = get_prompt("generate_profile")
        self._timeline_prompt = get_prompt("generate_timeline")

    # ------------------------------------------------------------------
    # Institution explainer
    # ------------------------------------------------------------------

    def explain_institution(
        self, institution_id: str, specific_topic: str = ""
    ) -> ExplainerResult:
        institution = self._get_institution(institution_id)
        data_block = _institution_to_text(institution)

        system, user = self._inst_prompt.render(
            institution_data=data_block,
            specific_topic=specific_topic or "Visão geral da instituição",
        )
        logger.info("Explaining institution: %s", institution_id)
        response = self.client.complete(
            system=system,
            user=user,
            model=self._inst_prompt.model,
            max_tokens=self._inst_prompt.max_tokens,
            temperature=self._inst_prompt.temperature,
        )
        return ExplainerResult.parse_institution(institution_id, response)

    # ------------------------------------------------------------------
    # Public figure profile
    # ------------------------------------------------------------------

    def generate_profile(self, figure_id: str) -> ProfileResult:
        figure = self._get_figure(figure_id)
        data_block = _figure_to_text(figure)
        # Collect events referencing this figure
        related_events = [
            ev
            for ev in self.kb.events.values()
            if any(a.figure_id == figure_id for a in (ev.actors or []))
        ]
        events_block = _events_to_text(related_events) if related_events else "Nenhum evento relacionado."

        system, user = self._profile_prompt.render(
            figure_data=data_block,
            related_events=events_block,
        )
        logger.info("Generating profile: %s", figure_id)
        response = self.client.complete(
            system=system,
            user=user,
            model=self._profile_prompt.model,
            max_tokens=self._profile_prompt.max_tokens,
            temperature=self._profile_prompt.temperature,
        )
        return ProfileResult.parse(figure_id, response)

    # ------------------------------------------------------------------
    # Timeline narrative
    # ------------------------------------------------------------------

    def generate_timeline(self, timeline_group: str) -> TimelineResult:
        from src.knowledge.graph import get_timeline_events  # noqa: PLC0415

        events = get_timeline_events(self.kb, timeline_group)
        if not events:
            raise ValueError(f"No events found for timeline group: {timeline_group!r}")

        events_block = _events_to_text(events)
        system, user = self._timeline_prompt.render(
            timeline_group=timeline_group,
            events_data=events_block,
        )
        logger.info("Generating timeline: %s", timeline_group)
        response = self.client.complete(
            system=system,
            user=user,
            model=self._timeline_prompt.model,
            max_tokens=self._timeline_prompt.max_tokens,
            temperature=self._timeline_prompt.temperature,
        )
        return TimelineResult.parse(timeline_group, response)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_institution(self, institution_id: str) -> Institution:
        inst = self.kb.institutions.get(institution_id)
        if not inst:
            available = list(self.kb.institutions.keys())
            raise ValueError(
                f"Institution {institution_id!r} not found. Available: {available}"
            )
        return inst

    def _get_figure(self, figure_id: str) -> PublicFigure:
        fig = self.kb.figures.get(figure_id)
        if not fig:
            available = list(self.kb.figures.keys())
            raise ValueError(f"Figure {figure_id!r} not found. Available: {available}")
        return fig


# ---------------------------------------------------------------------------
# Data serialisers (KB → readable text blocks)
# ---------------------------------------------------------------------------


def _institution_to_text(inst: Institution) -> str:
    parts = [
        f"Nome: {inst.name_common}",
        f"Nome oficial: {inst.name_official}",
        f"Sigla: {inst.acronym}",
        f"Tipo: {inst.type.value}",
        f"Jurisdição: {inst.jurisdiction}",
        f"Descrição: {inst.description}",
    ]
    if inst.established:
        parts.append(f"Fundação: {inst.established}")
    if inst.constitutional_basis:
        parts.append(f"Base constitucional: {inst.constitutional_basis}")
    if inst.composition:
        comp = inst.composition
        parts.append(f"Composição: {comp.total_members} membros")
        if comp.how_appointed:
            parts.append(f"Nomeação: {comp.how_appointed}")
        if comp.term_length:
            parts.append(f"Mandato: {comp.term_length}")
    if inst.key_functions:
        funcs = "\n".join(f"  - {f}" for f in inst.key_functions[:8])
        parts.append(f"Funções:\n{funcs}")
    if inst.tags:
        parts.append(f"Tags: {', '.join(inst.tags)}")
    return "\n".join(parts)


def _figure_to_text(fig: PublicFigure) -> str:
    parts = [
        f"Nome: {fig.full_name}",
    ]
    if fig.birth_date:
        parts.append(f"Data de nascimento: {fig.birth_date}")
    if fig.birth_place:
        parts.append(f"Local de nascimento: {fig.birth_place}")
    if fig.party_affiliations:
        current_party = next(
            (p.party for p in reversed(fig.party_affiliations) if p.end is None),
            fig.party_affiliations[-1].party if fig.party_affiliations else None,
        )
        if current_party:
            parts.append(f"Partido: {current_party}")
    if fig.current_role:
        parts.append(f"Cargo atual: {fig.current_role}")
    if fig.career:
        career_lines = "\n".join(
            f"  - {c.role} ({c.institution}, {c.start_date}–{c.end_date or 'atual'})"
            for c in fig.career[-6:]  # last 6 entries
        )
        parts.append(f"Carreira:\n{career_lines}")
    if fig.controversies:
        controv = "\n".join(
            f"  - {c.title} ({c.status.value}): {c.summary[:100]}"
            for c in fig.controversies[:5]
        )
        parts.append(f"Controvérsias:\n{controv}")
    if fig.public_positions:
        positions = "\n".join(
            f"  - {p.topic}: {p.position[:80]}"
            for p in fig.public_positions[:5]
        )
        parts.append(f"Posições públicas:\n{positions}")
    return "\n".join(p for p in parts if p)


def _events_to_text(events: list[Event]) -> str:
    parts = []
    for ev in sorted(events, key=lambda e: (e.date or "")):
        block = f"### {ev.title} ({ev.date or 'data desconhecida'})"
        block += f"\n{ev.summary}"
        if ev.significance:
            block += f"\nSignificância: {ev.significance}"
        if ev.detailed_description:
            block += f"\nDescrição: {ev.detailed_description[:200]}"
        parts.append(block)
    return "\n\n".join(parts)
