"""
Knowledge base full-text search.
Searches across all entity types and returns ranked results.
"""

from __future__ import annotations

from typing import Any

from .models import KnowledgeBase


def search_knowledge_base(
    kb: KnowledgeBase,
    query: str,
    limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """
    Search across all entity types in the knowledge base.
    Matches against names, descriptions, summaries, and tags.
    Returns results grouped by entity type.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return {"institutions": [], "figures": [], "events": [], "glossary": []}

    results: dict[str, list[dict[str, Any]]] = {
        "institutions": [],
        "figures": [],
        "events": [],
        "glossary": [],
    }

    # Search institutions
    for inst_id, inst in kb.institutions.items():
        score = 0
        if query_lower in inst.name_official.lower():
            score += 10
        if query_lower in inst.name_common.lower():
            score += 10
        if query_lower in inst.acronym.lower():
            score += 8
        if query_lower in inst.description.lower():
            score += 4
        if any(query_lower in tag.lower() for tag in inst.tags):
            score += 2
        if any(query_lower in fn.lower() for fn in inst.key_functions):
            score += 2

        if score > 0:
            results["institutions"].append({
                "id": inst_id,
                "name": inst.name_common,
                "acronym": inst.acronym,
                "type": inst.type.value,
                "description": inst.description[:200] + ("..." if len(inst.description) > 200 else ""),
                "score": score,
            })

    # Search figures
    for fig_id, fig in kb.figures.items():
        score = 0
        if query_lower in fig.full_name.lower():
            score += 10
        if any(query_lower in tag.lower() for tag in fig.tags):
            score += 3
        if any(query_lower in c.role.lower() for c in fig.career):
            score += 2
        if any(query_lower in c.institution.lower() for c in fig.career):
            score += 1
        if any(query_lower in con.title.lower() for con in fig.controversies):
            score += 2
        if any(query_lower in pos.topic.lower() for pos in fig.public_positions):
            score += 1

        if score > 0:
            results["figures"].append({
                "id": fig_id,
                "name": fig.full_name,
                "current_role": fig.current_role,
                "current_institution": fig.current_institution,
                "score": score,
            })

    # Search events
    for event_id, event in kb.events.items():
        score = 0
        if query_lower in event.title.lower():
            score += 10
        if query_lower in event.summary.lower():
            score += 5
        if event.detailed_description and query_lower in event.detailed_description.lower():
            score += 3
        if event.significance and query_lower in event.significance.lower():
            score += 2
        if any(query_lower in tag.lower() for tag in event.tags):
            score += 2
        if event.timeline_group and query_lower in event.timeline_group.lower():
            score += 3

        if score > 0:
            results["events"].append({
                "id": event_id,
                "title": event.title,
                "date": str(event.date),
                "type": event.type.value,
                "summary": event.summary[:200] + ("..." if len(event.summary) > 200 else ""),
                "score": score,
            })

    # Search glossary
    for term_id, term in kb.glossary.items():
        score = 0
        if query_lower in term.term_pt.lower():
            score += 10
        if term.term_en and query_lower in term.term_en.lower():
            score += 8
        if query_lower in term.definition.lower():
            score += 4
        if term.example and query_lower in term.example.lower():
            score += 2
        if any(query_lower in tag.lower() for tag in term.tags):
            score += 2

        if score > 0:
            results["glossary"].append({
                "id": term_id,
                "term_pt": term.term_pt,
                "term_en": term.term_en,
                "definition": term.definition[:200] + ("..." if len(term.definition) > 200 else ""),
                "score": score,
            })

    # Sort each category by score descending and apply limit
    for key in results:
        results[key] = sorted(results[key], key=lambda x: x["score"], reverse=True)[:limit]

    return results


def get_total_results(search_results: dict[str, list[dict[str, Any]]]) -> int:
    """Count total results across all categories."""
    return sum(len(v) for v in search_results.values())
