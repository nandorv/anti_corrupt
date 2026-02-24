#!/usr/bin/env python3
"""
export_graph.py
Export the knowledge base relationship graph as JSON or GEXF for external tools.
Usage: uv run python scripts/export_graph.py [--format json|gexf]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import networkx as nx
from rich.console import Console

from config.settings import settings
from src.knowledge.graph import build_graph, get_graph_stats
from src.knowledge.loader import load_knowledge_base

console = Console()


def export_json(G: nx.DiGraph, output_path: Path) -> None:
    """Export graph as node-link JSON (compatible with D3.js)."""
    data = nx.node_link_data(G)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"[green]✓[/green] Exported JSON to {output_path}")


def export_gexf(G: nx.DiGraph, output_path: Path) -> None:
    """Export graph as GEXF (compatible with Gephi and other graph tools)."""
    # GEXF requires string attribute values
    for node_id, data in G.nodes(data=True):
        for key, value in list(data.items()):
            if value is None:
                G.nodes[node_id][key] = ""
            elif not isinstance(value, (str, int, float, bool)):
                G.nodes[node_id][key] = str(value)
    nx.write_gexf(G, str(output_path))
    console.print(f"[green]✓[/green] Exported GEXF to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the knowledge graph")
    parser.add_argument(
        "--format", choices=["json", "gexf"], default="json", help="Output format"
    )
    parser.add_argument("--output", type=Path, default=None, help="Output file path")
    args = parser.parse_args()

    kb = load_knowledge_base(settings.data_dir)
    G = build_graph(kb)
    stats = get_graph_stats(G)

    console.print(
        f"\n[bold]Graph:[/bold] {stats['total_nodes']} nodes, {stats['total_edges']} edges\n"
    )

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if args.output:
        output_path = args.output
    else:
        output_path = output_dir / f"knowledge_graph.{args.format}"

    if args.format == "json":
        export_json(G, output_path)
    else:
        export_gexf(G, output_path)

    console.print(f"\n[dim]Open JSON in D3.js or GEXF in Gephi for visualization.[/dim]\n")


if __name__ == "__main__":
    main()
