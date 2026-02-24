"""
Relationship graph builder and query engine.
Uses NetworkX to represent the knowledge base as a directed graph.
"""

from __future__ import annotations

from typing import Any, Optional

import networkx as nx

from .models import KnowledgeBase


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph(kb: KnowledgeBase) -> nx.DiGraph:
    """
    Build a directed graph from the knowledge base.
    Nodes: institutions, figures, events
    Edges: relationships
    """
    G: nx.DiGraph = nx.DiGraph()

    # Add institution nodes
    for inst_id, inst in kb.institutions.items():
        G.add_node(
            inst_id,
            node_type="institution",
            label=inst.name_common,
            acronym=inst.acronym,
            inst_type=inst.type.value,
            description=inst.description,
            tags=inst.tags,
        )

    # Add figure nodes
    for fig_id, fig in kb.figures.items():
        G.add_node(
            fig_id,
            node_type="figure",
            label=fig.full_name,
            current_role=fig.current_role,
            current_institution=fig.current_institution,
            tags=fig.tags,
        )

    # Add event nodes
    for event_id, event in kb.events.items():
        G.add_node(
            event_id,
            node_type="event",
            label=event.title,
            date=str(event.date),
            event_type=event.type.value,
            tags=event.tags,
        )

    # Add relationship edges
    for rel in kb.relationships:
        # Add nodes if they don't exist yet (defensive — handles missing KB entries)
        if rel.source_id not in G:
            G.add_node(rel.source_id, node_type=rel.source_type.value, label=rel.source_id)
        if rel.target_id not in G:
            G.add_node(rel.target_id, node_type=rel.target_type.value, label=rel.target_id)

        G.add_edge(
            rel.source_id,
            rel.target_id,
            rel_id=rel.id,
            rel_type=rel.relationship_type.value,
            description=rel.description,
            strength=rel.strength.value,
            start_date=str(rel.start_date) if rel.start_date is not None else None,
            end_date=str(rel.end_date) if rel.end_date is not None else None,
        )

    return G


# ── Query functions ───────────────────────────────────────────────────────────

def get_entity_connections(
    G: nx.DiGraph,
    entity_id: str,
) -> dict[str, Any]:
    """
    Get all direct connections (incoming and outgoing) for an entity.
    Returns a dict with the entity's node data and its connections.
    """
    if entity_id not in G:
        return {"error": f"Entity '{entity_id}' not found in graph"}

    outgoing = []
    for target in G.successors(entity_id):
        edge_data = G.edges[entity_id, target]
        outgoing.append({
            "entity_id": target,
            "entity": dict(G.nodes[target]),
            "relationship": edge_data,
        })

    incoming = []
    for source in G.predecessors(entity_id):
        edge_data = G.edges[source, entity_id]
        incoming.append({
            "entity_id": source,
            "entity": dict(G.nodes[source]),
            "relationship": edge_data,
        })

    return {
        "entity_id": entity_id,
        "entity": dict(G.nodes[entity_id]),
        "outgoing": outgoing,
        "incoming": incoming,
        "degree": G.degree(entity_id),
    }


def find_path(
    G: nx.DiGraph,
    source_id: str,
    target_id: str,
) -> list[str]:
    """Find the shortest path between two entities (ignores direction)."""
    try:
        return nx.shortest_path(G.to_undirected(), source_id, target_id)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def get_nodes_by_type(
    G: nx.DiGraph,
    node_type: str,
    subtype: Optional[str] = None,
) -> list[str]:
    """
    Get all node IDs of a given type.
    node_type: "institution" | "figure" | "event"
    subtype: for institutions, the InstitutionType value (e.g., "judicial")
    """
    result = []
    for node_id, data in G.nodes(data=True):
        if data.get("node_type") == node_type:
            if subtype is None:
                result.append(node_id)
            elif data.get("inst_type") == subtype or data.get("event_type") == subtype:
                result.append(node_id)
    return result


def get_graph_stats(G: nx.DiGraph) -> dict[str, Any]:
    """Return summary statistics about the graph."""
    nodes_by_type: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        ntype = data.get("node_type", "unknown")
        nodes_by_type[ntype] = nodes_by_type.get(ntype, 0) + 1

    # Most connected nodes (by total degree)
    top_connected = sorted(
        [(node_id, G.degree(node_id), G.nodes[node_id].get("label", node_id))
         for node_id in G.nodes()],
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "nodes_by_type": nodes_by_type,
        "top_connected": [
            {"id": nid, "degree": deg, "label": label}
            for nid, deg, label in top_connected
        ],
        "is_connected": nx.is_weakly_connected(G) if G.number_of_nodes() > 0 else False,
    }


def get_timeline_events(
    kb: KnowledgeBase,
    timeline_group: str,
) -> list[Any]:
    """Return all events for a given timeline group, sorted by date."""
    events = [
        event for event in kb.events.values()
        if event.timeline_group == timeline_group
    ]
    return sorted(events, key=lambda e: e.date)
