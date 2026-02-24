"""
Public figure profile card generator.

Layout (1080×1080):
  ┌──────────────────────────────┐
  │ ████ accent bar              │
  │                              │
  │  PERFIL                      │  ← label
  │  FULL NAME (large, bold)     │  ← main name
  │  Current Role                │  ← subtitle
  │                              │
  │  ──────────────────────      │
  │                              │
  │  🏛  Partido / Filiação      │  ← facts section
  │  📅  Nascido em ...          │
  │  ⚖️  Cargo atual             │
  │                              │
  │  ──────────────────────      │
  │  Última controvérsia         │  ← controversy box (if any)
  │                              │
  │  @anticorrupt                │  ← footer
  │ ████ accent bar              │
  └──────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.knowledge.models import PublicFigure
from src.visuals.renderer import (
    DIMS,
    PALETTE,
    TextBlock,
    draw_accent_bar,
    draw_rounded_rect,
    draw_text_block,
    hex_to_rgb,
    institution_color,
    load_font,
    new_image,
    save_image,
)

_MARGIN = 72
_BAR = 10
_W, _H = DIMS["instagram_square"].size


def render_profile_card(
    figure: PublicFigure,
    output_path: Optional[Path] = None,
    accent_color: Optional[str] = None,
    handle: str = "@anticorrupt",
) -> Path:
    """
    Render a 1080×1080 profile card for a PublicFigure.

    Args:
        figure:       The PublicFigure Pydantic model.
        output_path:  Where to save the PNG. Defaults to output/images/profile_<id>.png.
        accent_color: Override accent color (auto-detected from career if not given).
        handle:       Social handle shown in footer.

    Returns:
        Path to the generated PNG file.
    """
    if output_path is None:
        output_path = Path("output/images") / f"profile_{figure.id}.png"

    # Pick accent color from current role institution type if not overridden
    if accent_color is None:
        accent_color = PALETTE["accent_default"]
        if figure.career:
            # Look for judicial/legislative/executive in institution names
            for entry in reversed(figure.career):
                name_lower = entry.institution.lower()
                if any(k in name_lower for k in ("tribunal", "stf", "tse", "trf")):
                    accent_color = PALETTE["accent_judiciary"]
                    break
                elif any(k in name_lower for k in ("senado", "câmara", "camara", "congresso")):
                    accent_color = PALETTE["accent_legislature"]
                    break
                elif any(k in name_lower for k in ("presidência", "presidencia", "governo")):
                    accent_color = PALETTE["accent_executive"]
                    break

    img, draw = new_image(DIMS["instagram_square"], PALETTE["background"])
    accent_rgb = hex_to_rgb(accent_color)

    # Accent bars
    draw.rectangle([0, 0, _W, _BAR], fill=accent_rgb)
    draw.rectangle([0, _H - _BAR, _W, _H], fill=accent_rgb)

    y = _BAR + 32

    # "PERFIL" label
    label_font = load_font(28, bold=False)
    draw.text((_MARGIN, y), "PERFIL", font=label_font, fill=accent_rgb)
    y += 44

    # Full name
    name_block = TextBlock(
        text=figure.full_name,
        x=_MARGIN,
        y=y,
        font_size=56,
        bold=True,
        color=PALETTE["text_primary"],
        max_width=_W - 2 * _MARGIN,
    )
    y = draw_text_block(draw, name_block) + 12

    # Current role subtitle
    current_role = figure.current_role or ""
    if current_role:
        role_block = TextBlock(
            text=current_role,
            x=_MARGIN,
            y=y,
            font_size=34,
            bold=False,
            color=accent_color,
            max_width=_W - 2 * _MARGIN,
        )
        y = draw_text_block(draw, role_block) + 20

    # Separator
    sep_rgb = hex_to_rgb(PALETTE["border"])
    draw.line([(_MARGIN, y), (_W - _MARGIN, y)], fill=sep_rgb, width=2)
    y += 24

    # Facts section
    facts: list[str] = []

    # Birth info
    if figure.birth_date:
        birth_str = str(figure.birth_date)
        if figure.birth_place:
            birth_str += f"  •  {figure.birth_place}"
        facts.append(f"📅  {birth_str}")

    # Party affiliation (most recent)
    if figure.party_affiliations:
        current_party = next(
            (p for p in reversed(figure.party_affiliations) if p.end is None),
            figure.party_affiliations[-1] if figure.party_affiliations else None,
        )
        if current_party:
            facts.append(f"🏛️  {current_party.party}")

    # Career: last 2 roles
    if figure.career:
        recent = list(reversed(figure.career))[:2]
        for entry in recent:
            role_line = f"• {entry.role} — {entry.institution}"
            facts.append(role_line)

    for fact in facts:
        fact_block = TextBlock(
            text=fact,
            x=_MARGIN,
            y=y,
            font_size=30,
            color=PALETTE["text_secondary"],
            max_width=_W - 2 * _MARGIN,
        )
        y = draw_text_block(draw, fact_block) + 8

    y += 12

    # Most recent controversy (if any), in a rounded box
    if figure.controversies:
        controversy = figure.controversies[-1]
        box_pad = 24
        box_x1, box_y1 = _MARGIN, y
        box_x2 = _W - _MARGIN

        # Draw box first (estimate height)
        box_h = 110
        draw_rounded_rect(
            draw,
            (box_x1, box_y1, box_x2, box_y1 + box_h),
            radius=12,
            fill="#FFF5F5",
            outline="#FC8181",
            outline_width=2,
        )

        # Box title
        ctitle_font = load_font(24, bold=True)
        draw.text(
            (box_x1 + box_pad, box_y1 + box_pad),
            f"⚠️  {controversy.title}",
            font=ctitle_font,
            fill=hex_to_rgb("#9B2C2C"),
        )

        # Status pill
        status_font = load_font(22)
        draw.text(
            (box_x1 + box_pad, box_y1 + box_pad + 40),
            f"Status: {controversy.status}",
            font=status_font,
            fill=hex_to_rgb(PALETTE["text_muted"]),
        )
        y = box_y1 + box_h + 20

    # Footer
    footer_y = _H - _BAR - 56
    draw.line([(_MARGIN, footer_y - 12), (_W - _MARGIN, footer_y - 12)], fill=sep_rgb, width=1)
    footer_font = load_font(28)
    draw.text((_MARGIN, footer_y), handle, font=footer_font, fill=hex_to_rgb(PALETTE["text_muted"]))

    # "anticorrupt.dev" right-aligned
    brand_text = "anticorrupt.dev"
    brand_font = load_font(26)
    brand_w = (
        draw.textlength(brand_text, font=brand_font)
        if hasattr(draw, "textlength")
        else len(brand_text) * 15
    )
    draw.text(
        (_W - _MARGIN - int(brand_w), footer_y),
        brand_text,
        font=brand_font,
        fill=accent_rgb,
    )

    return save_image(img, output_path)
