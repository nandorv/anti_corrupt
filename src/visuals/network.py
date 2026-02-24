"""
Network / relationship graph visualizer.

Uses NetworkX to build a subgraph centered on an entity, then renders it
with matplotlib to a PNG (1200×675 landscape).

Node color encodes entity type:
  - institution → accent_judiciary / accent_legislature / accent_executive
  - figure      → teal (#2C7A7B)
  - event       → orange (#C05621)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.visuals.renderer import PALETTE, hex_to_rgb, save_image

# Use Agg backend (no display needed — works in CI / headless)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

_NODE_COLORS = {
    "institution": "#1A365D",
    "figure": "#2C7A7B",
    "event": "#C05621",
    "glossary": "#553C9A",
    "default": "#4A5568",
}

_EDGE_COLORS = {
    "appointed_by": "#975A16",
    "member_of": "#276749",
    "ruled_on": "#1A365D",
    "investigated": "#9B2C2C",
    "default": "#A0AEC0",
}


def render_network(
    graph: nx.DiGraph,
    center_node: Optional[str] = None,
    title: str = "Mapa de Relações",
    depth: int = 2,
    output_path: Optional[Path] = None,
    accent_color: Optional[str] = None,
    handle: str = "@anticorrupt",
    figsize: tuple[int, int] = (14, 8),
) -> Path:
    """
    Render a network diagram from a NetworkX graph.

    Args:
        graph:        The full relationship graph (from KnowledgeGraph).
        center_node:  If provided, render only the subgraph within `depth` hops.
        title:        Chart title shown at the top.
        depth:        How many hops from center_node to include.
        output_path:  Where to save the PNG.
        accent_color: Override title/accent color.
        handle:       Social handle shown in footer.
        figsize:      Matplotlib figure size in inches.

    Returns:
        Path to the saved PNG.
    """
    if output_path is None:
        slug = center_node or "network"
        output_path = Path("output/images") / f"network_{slug}.png"

    accent = accent_color or PALETTE["accent_default"]

    # Subgraph extraction
    if center_node and center_node in graph:
        nodes = set()
        for d in range(depth + 1):
            shell = nx.single_source_shortest_path_length(graph.to_undirected(), center_node, cutoff=d)
            nodes.update(shell.keys())
        subgraph: nx.DiGraph = graph.subgraph(nodes).copy()
    else:
        subgraph = graph

    if len(subgraph.nodes) == 0:
        # Empty graph — just save a blank image with message
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "Sem dados suficientes para o diagrama.", ha="center", va="center", fontsize=16)
        ax.axis("off")
        _finalize_and_save(fig, output_path, title, accent, handle)
        return output_path

    # Node colors and labels
    node_colors = []
    node_labels = {}
    for node in subgraph.nodes:
        data = subgraph.nodes[node]
        entity_type = data.get("type", "default")
        node_colors.append(_NODE_COLORS.get(entity_type, _NODE_COLORS["default"]))
        label = data.get("label", node)
        # Truncate long labels
        if len(label) > 20:
            label = label[:18] + "…"
        node_labels[node] = label

    # Edge colors
    edge_colors = []
    for u, v, data in subgraph.edges(data=True):
        rel_type = data.get("relationship_type", "default")
        edge_colors.append(_EDGE_COLORS.get(rel_type, _EDGE_COLORS["default"]))

    # Layout
    if len(subgraph.nodes) <= 10:
        pos = nx.spring_layout(subgraph, k=2.5, seed=42)
    else:
        pos = nx.kamada_kawai_layout(subgraph)

    # Plot
    fig, ax = plt.subplots(figsize=figsize, facecolor=PALETTE["background"])
    ax.set_facecolor(PALETTE["background"])

    # Draw edges first (behind nodes)
    nx.draw_networkx_edges(
        subgraph, pos,
        ax=ax,
        edge_color=edge_colors,
        alpha=0.6,
        arrows=True,
        arrowsize=20,
        width=1.5,
        connectionstyle="arc3,rad=0.1",
    )

    # Highlight center node
    node_sizes = []
    for node in subgraph.nodes:
        node_sizes.append(1800 if node == center_node else 1200)

    nx.draw_networkx_nodes(
        subgraph, pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.92,
    )

    # Center node border
    if center_node and center_node in subgraph:
        center_pos = {center_node: pos[center_node]}
        nx.draw_networkx_nodes(
            subgraph.subgraph([center_node]), center_pos,
            ax=ax,
            node_color=[accent],
            node_size=[2200],
            alpha=1.0,
        )

    nx.draw_networkx_labels(
        subgraph, pos,
        labels=node_labels,
        ax=ax,
        font_size=9,
        font_color="white",
        font_weight="bold",
    )

    # Legend
    legend_patches = [
        mpatches.Patch(color=_NODE_COLORS["institution"], label="Instituição"),
        mpatches.Patch(color=_NODE_COLORS["figure"], label="Figura pública"),
        mpatches.Patch(color=_NODE_COLORS["event"], label="Evento"),
    ]
    ax.legend(handles=legend_patches, loc="lower left", fontsize=9, framealpha=0.7)
    ax.axis("off")

    _finalize_and_save(fig, output_path, title, accent, handle)
    return output_path


def _finalize_and_save(
    fig: plt.Figure,
    output_path: Path,
    title: str,
    accent: str,
    handle: str,
) -> None:
    """Add title/footer and save the figure."""
    r, g, b = hex_to_rgb(accent)
    accent_mpl = (r / 255, g / 255, b / 255)

    fig.suptitle(title, fontsize=18, fontweight="bold", color=accent_mpl, y=0.97)
    fig.text(0.99, 0.01, handle, ha="right", va="bottom", fontsize=9, color="#718096")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
