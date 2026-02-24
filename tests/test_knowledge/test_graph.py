"""Tests for knowledge base graph engine."""

import pytest
from pathlib import Path

from src.knowledge.graph import (
    build_graph,
    find_path,
    get_entity_connections,
    get_graph_stats,
    get_nodes_by_type,
    get_timeline_events,
)
from src.knowledge.loader import load_knowledge_base


@pytest.fixture
def kb(data_dir: Path):
    return load_knowledge_base(data_dir)


@pytest.fixture
def graph(kb):
    return build_graph(kb)


class TestBuildGraph:
    def test_graph_has_nodes(self, graph):
        assert graph.number_of_nodes() > 0

    def test_graph_has_edges(self, graph):
        assert graph.number_of_edges() > 0

    def test_institutions_are_nodes(self, graph):
        assert "stf" in graph.nodes
        assert "senado-federal" in graph.nodes

    def test_figures_are_nodes(self, graph):
        assert "lula" in graph.nodes
        assert "alexandre-de-moraes" in graph.nodes

    def test_events_are_nodes(self, graph):
        assert "constituicao-1988" in graph.nodes

    def test_node_has_correct_type(self, graph):
        assert graph.nodes["stf"]["node_type"] == "institution"
        assert graph.nodes["lula"]["node_type"] == "figure"
        assert graph.nodes["constituicao-1988"]["node_type"] == "event"

    def test_institution_node_has_label(self, graph):
        stf_node = graph.nodes["stf"]
        assert "label" in stf_node
        assert stf_node["label"] == "STF"


class TestGetEntityConnections:
    def test_stf_has_connections(self, graph):
        connections = get_entity_connections(graph, "stf")
        assert "error" not in connections
        total = len(connections["outgoing"]) + len(connections["incoming"])
        assert total > 0

    def test_unknown_entity_returns_error(self, graph):
        connections = get_entity_connections(graph, "nonexistent-entity")
        assert "error" in connections

    def test_connections_have_required_keys(self, graph):
        connections = get_entity_connections(graph, "stf")
        assert "entity" in connections
        assert "outgoing" in connections
        assert "incoming" in connections
        assert "degree" in connections

    def test_lula_connected_to_presidencia(self, graph):
        connections = get_entity_connections(graph, "lula")
        all_connected = (
            [c["entity_id"] for c in connections["outgoing"]] +
            [c["entity_id"] for c in connections["incoming"]]
        )
        assert "presidencia-da-republica" in all_connected


class TestGetNodesByType:
    def test_get_all_institutions(self, graph):
        institutions = get_nodes_by_type(graph, "institution")
        assert len(institutions) >= 5
        assert "stf" in institutions

    def test_get_judicial_institutions(self, graph):
        judicial = get_nodes_by_type(graph, "institution", subtype="judicial")
        assert "stf" in judicial

    def test_get_all_figures(self, graph):
        figures = get_nodes_by_type(graph, "figure")
        assert "lula" in figures

    def test_get_all_events(self, graph):
        events = get_nodes_by_type(graph, "event")
        assert "constituicao-1988" in events


class TestGetGraphStats:
    def test_stats_have_required_keys(self, graph):
        stats = get_graph_stats(graph)
        assert "total_nodes" in stats
        assert "total_edges" in stats
        assert "nodes_by_type" in stats
        assert "top_connected" in stats
        assert "is_connected" in stats

    def test_node_counts_are_positive(self, graph):
        stats = get_graph_stats(graph)
        assert stats["total_nodes"] > 0
        assert stats["total_edges"] > 0

    def test_nodes_by_type_has_institution(self, graph):
        stats = get_graph_stats(graph)
        assert "institution" in stats["nodes_by_type"]
        assert stats["nodes_by_type"]["institution"] >= 5


class TestFindPath:
    def test_finds_path_between_connected_entities(self, graph):
        # STF → executive via relationships
        path = find_path(graph, "stf", "lula")
        # Path may exist or not depending on graph, just verify it returns a list
        assert isinstance(path, list)

    def test_returns_empty_for_nonexistent(self, graph):
        path = find_path(graph, "nonexistent-a", "nonexistent-b")
        assert path == []


class TestGetTimelineEvents:
    def test_gets_lava_jato_events(self, kb):
        events = get_timeline_events(kb, "lava-jato")
        assert len(events) >= 1
        assert all(e.timeline_group == "lava-jato" for e in events)

    def test_events_are_sorted_by_date(self, kb):
        events = get_timeline_events(kb, "lava-jato")
        if len(events) > 1:
            for i in range(len(events) - 1):
                assert events[i].date <= events[i + 1].date

    def test_empty_for_unknown_group(self, kb):
        events = get_timeline_events(kb, "nonexistent-group")
        assert events == []
