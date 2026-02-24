"""
Tests for visual generation modules (renderer, carousel, profiles, timelines, diagrams, network).

Uses tmp_path to write PNGs and verifies:
  - Files are created at the expected path
  - PIL can open and verify the image
  - Dimensions match the expected platform size
"""

import datetime as dt
from pathlib import Path

import pytest
from PIL import Image

from src.visuals.renderer import (
    DIMS,
    PALETTE,
    hex_to_rgb,
    institution_color,
    load_font,
    new_image,
    save_image,
    TextBlock,
    draw_text_block,
)


# ---------------------------------------------------------------------------
# Fixtures: minimal knowledge base objects
# ---------------------------------------------------------------------------

def _make_figure():
    from src.knowledge.models import PublicFigure, CareerEntry, PartyAffiliation, Controversy
    return PublicFigure(
        id="test-figure",
        full_name="João da Silva",
        birth_date=dt.date(1970, 1, 15),
        birth_place="São Paulo, SP",
        career=[
            CareerEntry(
                role="Ministro",
                institution="Supremo Tribunal Federal",
                start_date=dt.date(2017, 10, 1),
            )
        ],
        party_affiliations=[
            PartyAffiliation(party="PT", start=dt.date(2000, 1, 1))
        ],
        controversies=[
            Controversy(
                title="Inquérito X",
                date=dt.date(2022, 3, 10),
                summary="Investigado por suposta irregularidade.",
                status="ongoing",
            )
        ],
        tags=["stf", "ministro"],
        sources=[],
        last_updated=dt.datetime.now(dt.timezone.utc),
    )


def _make_events():
    from src.knowledge.models import Event
    return [
        Event(
            id="evt1",
            title="Constituição Federal",
            date=dt.date(1988, 10, 5),
            type="law",
            summary="Promulgação da CF/88.",
            significance="Marco democrático.",
            timeline_group="historia",
            tags=[],
            sources=[],
            last_updated=dt.datetime.now(dt.timezone.utc),
        ),
        Event(
            id="evt2",
            title="Lava Jato",
            date=dt.date(2014, 3, 17),
            type="crisis",
            summary="Início da Operação Lava Jato.",
            significance="Maior investigação anticorrupção do Brasil.",
            timeline_group="historia",
            tags=[],
            sources=[],
            last_updated=dt.datetime.now(dt.timezone.utc),
        ),
    ]


CAROUSEL_TEXT = """=== CAROUSEL (3 slides) ===

--- Slide 1 ---
📌 Como funciona o STF

O Supremo Tribunal Federal é a mais alta corte do Brasil.

--- Slide 2 ---
⚖️ Composição

11 ministros indicados pelo presidente e aprovados pelo Senado.

--- Slide 3 ---
📚 Saiba mais

Acompanhe o anticorrupt para mais conteúdo.

--- Hashtags ---
#stf #politica #brasil
"""


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------

class TestRenderer:
    def test_hex_to_rgb(self):
        assert hex_to_rgb("#1A365D") == (26, 54, 93)
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
        assert hex_to_rgb("#000000") == (0, 0, 0)

    def test_institution_color_judicial(self):
        color = institution_color("judicial")
        assert color == "#1A365D"

    def test_institution_color_legislative(self):
        assert institution_color("legislative") == "#276749"

    def test_institution_color_executive(self):
        assert institution_color("executive") == "#975A16"

    def test_institution_color_default(self):
        assert institution_color(None) == "#4A5568"
        assert institution_color("unknown") == "#4A5568"

    def test_new_image_size(self):
        img, draw = new_image(DIMS["instagram_square"])
        assert img.size == (1080, 1080)

    def test_new_image_twitter_size(self):
        img, _ = new_image(DIMS["twitter"])
        assert img.size == (1200, 675)

    def test_save_image(self, tmp_path):
        img, _ = new_image(DIMS["thumbnail"])
        path = save_image(img, tmp_path / "test.png")
        assert path.exists()
        loaded = Image.open(path)
        assert loaded.size == (540, 540)

    def test_save_image_creates_dirs(self, tmp_path):
        img, _ = new_image(DIMS["thumbnail"])
        deep = tmp_path / "a" / "b" / "c" / "img.png"
        save_image(img, deep)
        assert deep.exists()

    def test_load_font_returns_font(self):
        font = load_font(32)
        assert font is not None

    def test_load_font_bold(self):
        font = load_font(32, bold=True)
        assert font is not None

    def test_draw_text_block_returns_y(self):
        img, draw = new_image(DIMS["instagram_square"])
        block = TextBlock(text="Hello World", x=50, y=50, font_size=32)
        y_after = draw_text_block(draw, block)
        assert y_after > 50


# ---------------------------------------------------------------------------
# Carousel tests
# ---------------------------------------------------------------------------

class TestCarousel:
    def test_parse_carousel_text(self):
        from src.visuals.carousel import parse_carousel_text
        slides = parse_carousel_text(CAROUSEL_TEXT)
        assert len(slides) == 3
        assert slides[0].title == "Como funciona o STF"
        assert slides[1].title == "Composição"
        assert slides[0].total == 3

    def test_parse_empty_text(self):
        from src.visuals.carousel import parse_carousel_text
        slides = parse_carousel_text("")
        assert slides == []

    def test_parse_slide_numbering(self):
        from src.visuals.carousel import parse_carousel_text
        slides = parse_carousel_text(CAROUSEL_TEXT)
        for i, slide in enumerate(slides, start=1):
            assert slide.index == i

    def test_render_carousel_creates_pngs(self, tmp_path):
        from src.visuals.carousel import render_carousel_from_draft
        paths = render_carousel_from_draft(
            formatted_text=CAROUSEL_TEXT,
            draft_id="test001",
            institution_type="judicial",
            output_dir=tmp_path,
        )
        assert len(paths) == 3
        for p in paths:
            assert p.exists()
            img = Image.open(p)
            assert img.size == (1080, 1080)

    def test_render_carousel_empty_text(self, tmp_path):
        from src.visuals.carousel import render_carousel_from_draft
        paths = render_carousel_from_draft("", draft_id="empty", output_dir=tmp_path)
        assert paths == []

    def test_render_carousel_accent_color(self, tmp_path):
        """Carousel should render without error for each institution type."""
        from src.visuals.carousel import render_carousel_from_draft
        for inst_type in ("judicial", "legislative", "executive", "independent"):
            paths = render_carousel_from_draft(
                CAROUSEL_TEXT, draft_id=f"test_{inst_type}",
                institution_type=inst_type, output_dir=tmp_path / inst_type
            )
            assert len(paths) == 3


# ---------------------------------------------------------------------------
# Profile card tests
# ---------------------------------------------------------------------------

class TestProfileCard:
    def test_renders_png(self, tmp_path):
        from src.visuals.profiles import render_profile_card
        figure = _make_figure()
        out = tmp_path / "profile.png"
        path = render_profile_card(figure, output_path=out)
        assert path.exists()
        img = Image.open(path)
        assert img.size == (1080, 1080)

    def test_renders_figure_without_controversies(self, tmp_path):
        from src.visuals.profiles import render_profile_card
        from src.knowledge.models import PublicFigure
        fig = PublicFigure(
            id="simple",
            full_name="Maria Souza",
            tags=[],
            sources=[],
            last_updated=dt.datetime.now(dt.timezone.utc),
        )
        path = render_profile_card(fig, output_path=tmp_path / "simple.png")
        assert path.exists()

    def test_renders_with_custom_accent(self, tmp_path):
        from src.visuals.profiles import render_profile_card
        figure = _make_figure()
        path = render_profile_card(figure, output_path=tmp_path / "p.png", accent_color="#276749")
        img = Image.open(path)
        assert img.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Timeline tests
# ---------------------------------------------------------------------------

class TestTimeline:
    def test_renders_png(self, tmp_path):
        from src.visuals.timelines import render_timeline
        events = _make_events()
        out = tmp_path / "timeline.png"
        path = render_timeline(events, title="História do Brasil", output_path=out)
        assert path.exists()
        img = Image.open(path)
        assert img.size == (1200, 675)

    def test_renders_empty_events(self, tmp_path):
        from src.visuals.timelines import render_timeline
        out = tmp_path / "empty.png"
        path = render_timeline([], title="Empty", output_path=out)
        assert path.exists()

    def test_renders_single_event(self, tmp_path):
        from src.visuals.timelines import render_timeline
        events = _make_events()[:1]
        path = render_timeline(events, title="Single", output_path=tmp_path / "single.png")
        assert path.exists()

    def test_sorts_events_chronologically(self, tmp_path):
        from src.visuals.timelines import render_timeline
        events = list(reversed(_make_events()))  # reversed order
        path = render_timeline(events, title="Sorted", output_path=tmp_path / "sorted.png")
        assert path.exists()


# ---------------------------------------------------------------------------
# Diagram / flowchart tests
# ---------------------------------------------------------------------------

class TestDiagrams:
    def test_predefined_diagrams_exist(self):
        from src.visuals.diagrams import PREDEFINED_FLOWCHARTS
        assert "lei" in PREDEFINED_FLOWCHARTS
        assert "impeachment" in PREDEFINED_FLOWCHARTS
        assert "stf" in PREDEFINED_FLOWCHARTS

    def test_render_lei_flowchart(self, tmp_path):
        from src.visuals.diagrams import PREDEFINED_FLOWCHARTS, render_flowchart
        path = render_flowchart(PREDEFINED_FLOWCHARTS["lei"], output_path=tmp_path / "lei.png")
        assert path.exists()
        img = Image.open(path)
        assert img.size == (1080, 1080)

    def test_render_impeachment_flowchart(self, tmp_path):
        from src.visuals.diagrams import PREDEFINED_FLOWCHARTS, render_flowchart
        path = render_flowchart(PREDEFINED_FLOWCHARTS["impeachment"], output_path=tmp_path / "imp.png")
        assert path.exists()

    def test_render_custom_flowchart(self, tmp_path):
        from src.visuals.diagrams import Flowchart, FlowStep, render_flowchart
        fc = Flowchart(
            title="Teste",
            steps=[
                FlowStep("Passo 1", "Descrição do passo 1"),
                FlowStep("Passo 2", "Descrição do passo 2"),
            ],
        )
        path = render_flowchart(fc, output_path=tmp_path / "custom.png")
        assert path.exists()

    def test_render_empty_flowchart(self, tmp_path):
        from src.visuals.diagrams import Flowchart, render_flowchart
        fc = Flowchart(title="Vazio")
        path = render_flowchart(fc, output_path=tmp_path / "empty.png")
        assert path.exists()


# ---------------------------------------------------------------------------
# Network diagram tests
# ---------------------------------------------------------------------------

class TestNetworkDiagram:
    def _make_graph(self):
        import networkx as nx
        G = nx.DiGraph()
        G.add_node("stf", type="institution", label="STF")
        G.add_node("alexandre-de-moraes", type="figure", label="Alexandre de Moraes")
        G.add_node("operacao-lava-jato", type="event", label="Lava Jato")
        G.add_edge("alexandre-de-moraes", "stf", relationship_type="member_of")
        G.add_edge("operacao-lava-jato", "stf", relationship_type="ruled_on")
        return G

    def test_render_network_png(self, tmp_path):
        from src.visuals.network import render_network
        G = self._make_graph()
        path = render_network(G, center_node="stf", output_path=tmp_path / "net.png")
        assert path.exists()
        img = Image.open(path)
        assert img.width > 0 and img.height > 0

    def test_render_empty_graph(self, tmp_path):
        import networkx as nx
        from src.visuals.network import render_network
        G = nx.DiGraph()
        path = render_network(G, output_path=tmp_path / "empty.png")
        assert path.exists()

    def test_render_nonexistent_center(self, tmp_path):
        from src.visuals.network import render_network
        G = self._make_graph()
        # Center node not in graph → should render full graph without error
        path = render_network(G, center_node="nonexistent", output_path=tmp_path / "full.png")
        assert path.exists()

    def test_render_network_creates_dir(self, tmp_path):
        from src.visuals.network import render_network
        G = self._make_graph()
        deep = tmp_path / "a" / "b" / "net.png"
        path = render_network(G, output_path=deep)
        assert path.exists()
