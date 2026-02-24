"""
Institutional flowchart / process diagram renderer.

Renders "how does X work" diagrams entirely with Pillow — no Graphviz needed.
Uses a vertical flow of step boxes connected by arrows.

Layout (1080×1080):
  ┌─────────────────────────────────────────────────────┐
  │ ████ accent bar                                     │
  │                                                     │
  │  COMO FUNCIONA:                                     │
  │  TÍTULO DO PROCESSO                                 │
  │                                                     │
  │  ┌──────────────────────────────────────────┐      │
  │  │  1. Passo um                              │      │
  │  └──────────────────────────────────────────┘      │
  │                      │                             │
  │                      ▼                             │
  │  ┌──────────────────────────────────────────┐      │
  │  │  2. Passo dois                            │      │
  │  └──────────────────────────────────────────┘      │
  │  ...                                               │
  │  @anticorrupt                                      │
  │ ████ accent bar                                    │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.visuals.renderer import (
    DIMS,
    PALETTE,
    draw_rounded_rect,
    hex_to_rgb,
    load_font,
    new_image,
    save_image,
)

_W, _H = DIMS["instagram_square"].size
_MARGIN = 72
_BAR = 10


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FlowStep:
    """A single step in a flowchart."""
    label: str
    description: str = ""
    color: Optional[str] = None     # box fill color; defaults to accent
    is_decision: bool = False        # future: diamond shape


@dataclass
class Flowchart:
    """A complete flowchart definition."""
    title: str
    subtitle: str = ""
    steps: list[FlowStep] = field(default_factory=list)
    accent_color: str = PALETTE["accent_default"]


# ---------------------------------------------------------------------------
# Predefined flowcharts
# ---------------------------------------------------------------------------

def how_a_law_is_passed() -> Flowchart:
    """Returns the flowchart for the Brazilian legislative process."""
    return Flowchart(
        title="Como uma lei é aprovada",
        subtitle="Processo legislativo no Brasil",
        accent_color=PALETTE["accent_legislature"],
        steps=[
            FlowStep("1. Apresentação", "Deputado, senador ou presidente apresenta o projeto de lei (PL)"),
            FlowStep("2. Comissões", "PL é analisado por comissões temáticas da Câmara"),
            FlowStep("3. Plenário da Câmara", "Votação pelos 513 deputados (maioria simples)"),
            FlowStep("4. Senado Federal", "PL vai ao Senado — votação pelos 81 senadores"),
            FlowStep("5. Sanção ou Veto", "Presidente sanciona (aprova) ou veta o projeto"),
            FlowStep("6. Publicação", "Lei publicada no Diário Oficial da União"),
        ],
    )


def how_impeachment_works() -> Flowchart:
    return Flowchart(
        title="Como funciona o impeachment",
        subtitle="Processo de impedimento presidencial",
        accent_color=PALETTE["accent_judiciary"],
        steps=[
            FlowStep("1. Denúncia", "Qualquer cidadão pode apresentar denúncia à Câmara"),
            FlowStep("2. Comissão especial", "Câmara cria comissão para analisar a denúncia"),
            FlowStep("3. Votação na Câmara", "2/3 dos deputados (342 de 513) devem aprovar"),
            FlowStep("4. Julgamento no Senado", "Senado julga — STF preside o processo"),
            FlowStep("5. Afastamento", "Com maioria simples, presidente é afastado por até 180 dias"),
            FlowStep("6. Condenação", "2/3 do Senado (54 de 81) condena — perda do mandato"),
        ],
    )


def how_stf_works() -> Flowchart:
    return Flowchart(
        title="Como funciona o STF",
        subtitle="Supremo Tribunal Federal",
        accent_color=PALETTE["accent_judiciary"],
        steps=[
            FlowStep("Composição", "11 ministros, indicados pelo presidente, aprovados pelo Senado"),
            FlowStep("Mandato", "Vitalício (até 75 anos de idade)"),
            FlowStep("Competências", "Guarda a Constituição, julga ações diretas de inconstitucionalidade"),
            FlowStep("Quórum", "Mínimo 6 ministros para julgamentos; maioria absoluta para decisões"),
            FlowStep("Recurso final", "Última instância do Judiciário — sem recurso após decisão do Plenário"),
        ],
    )


PREDEFINED_FLOWCHARTS: dict[str, Flowchart] = {
    "lei": how_a_law_is_passed(),
    "impeachment": how_impeachment_works(),
    "stf": how_stf_works(),
}


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_flowchart(
    flowchart: Flowchart,
    output_path: Optional[Path] = None,
    handle: str = "@anticorrupt",
) -> Path:
    """
    Render a Flowchart to a 1080×1080 PNG.
    Returns the path to the saved file.
    """
    if output_path is None:
        slug = flowchart.title.lower().replace(" ", "_")[:30]
        output_path = Path("output/images") / f"diagram_{slug}.png"

    accent = flowchart.accent_color
    accent_rgb = hex_to_rgb(accent)
    img, draw = new_image(DIMS["instagram_square"], PALETTE["background"])

    # Accent bars
    draw.rectangle([0, 0, _W, _BAR], fill=accent_rgb)
    draw.rectangle([0, _H - _BAR, _W, _H], fill=accent_rgb)

    y = _BAR + 28

    # "COMO FUNCIONA:" label
    label_font = load_font(26)
    draw.text((_MARGIN, y), "COMO FUNCIONA:", font=label_font, fill=accent_rgb)
    y += 40

    # Title
    title_font = load_font(46, bold=True)
    _draw_wrapped(draw, flowchart.title, _MARGIN, y, title_font, PALETTE["text_primary"], max_width=_W - 2 * _MARGIN)
    # Estimate title height
    title_lines = max(1, len(flowchart.title) // 22 + 1)
    y += title_lines * 56 + 8

    # Subtitle
    if flowchart.subtitle:
        sub_font = load_font(28)
        draw.text((_MARGIN, y), flowchart.subtitle, font=sub_font, fill=hex_to_rgb(accent))
        y += 40

    y += 8

    # Steps
    n_steps = len(flowchart.steps)
    available_h = _H - _BAR - 70 - y  # space for footer
    box_h = min(90, max(60, available_h // max(1, n_steps) - 20))
    box_w = _W - 2 * _MARGIN
    arrow_h = 20

    for i, step in enumerate(flowchart.steps):
        box_color = step.color or "#EBF8FF"
        border_color = step.color or accent

        # Box
        draw_rounded_rect(
            draw,
            (_MARGIN, y, _MARGIN + box_w, y + box_h),
            radius=10,
            fill=box_color,
            outline=border_color,
            outline_width=2,
        )

        # Step label
        step_font = load_font(26, bold=True)
        draw.text(
            (_MARGIN + 16, y + 10),
            step.label,
            font=step_font,
            fill=hex_to_rgb(PALETTE["text_primary"]),
        )

        # Step description (smaller, below label)
        if step.description and box_h > 65:
            desc_font = load_font(22)
            _draw_wrapped(
                draw,
                step.description,
                _MARGIN + 16,
                y + 42,
                desc_font,
                PALETTE["text_secondary"],
                max_width=box_w - 32,
            )

        y += box_h

        # Arrow between steps (except after last)
        if i < n_steps - 1:
            arrow_x = _W // 2
            draw.line([(arrow_x, y + 2), (arrow_x, y + arrow_h - 4)], fill=accent_rgb, width=3)
            # Arrowhead
            tip = y + arrow_h
            draw.polygon(
                [(arrow_x - 8, tip - 8), (arrow_x + 8, tip - 8), (arrow_x, tip)],
                fill=accent_rgb,
            )
            y += arrow_h + 4

    # Footer
    footer_y = _H - _BAR - 50
    draw.line([(_MARGIN, footer_y - 10), (_W - _MARGIN, footer_y - 10)],
              fill=hex_to_rgb(PALETTE["border"]), width=1)
    footer_font = load_font(26)
    draw.text((_MARGIN, footer_y), handle, font=footer_font, fill=hex_to_rgb(PALETTE["text_muted"]))

    return save_image(img, output_path)


def _draw_wrapped(draw, text: str, x: int, y: int, font, color: str, max_width: int) -> int:
    """Draw wrapped text, return y after last line."""
    import textwrap
    color_rgb = hex_to_rgb(color)
    avg_w = font.getlength("M") if hasattr(font, "getlength") else 14
    chars = max(10, int(max_width / avg_w))
    lines = textwrap.wrap(text, width=chars)
    lh = int(font.size * 1.3) if hasattr(font, "size") else 28
    for line in lines:
        draw.text((x, y), line, font=font, fill=color_rgb)
        y += lh
    return y
