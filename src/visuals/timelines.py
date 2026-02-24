"""
Visual timeline renderer.

Renders a horizontal (or vertical) timeline from a list of Event objects.

Layout (1200×675 — Twitter/landscape):
  ┌─────────────────────────────────────────────────────────────────────┐
  │  TITLE                                         @anticorrupt        │
  │  ─────────────────────────────────────────────────────────────     │
  │                                                                    │
  │   1988          2002          2016          2023                   │
  │    │             │             │             │                     │
  │  ──●─────────────●─────────────●─────────────●──────────────      │
  │    │             │             │             │                     │
  │  CF 1988      Lula eleito   Temer/Dilma   Lula eleito             │
  │  (card)       (card)         (card)        (card)                 │
  │                                                                    │
  └─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.knowledge.models import Event
from src.visuals.renderer import (
    DIMS,
    PALETTE,
    hex_to_rgb,
    load_font,
    new_image,
    save_image,
)

_W, _H = DIMS["twitter"].size  # 1200 × 675 — landscape for timelines
_MARGIN = 60
_ACCENT_BAR = 8


def render_timeline(
    events: list[Event],
    title: str = "Timeline",
    accent_color: Optional[str] = None,
    output_path: Optional[Path] = None,
    handle: str = "@anticorrupt",
) -> Path:
    """
    Render a horizontal timeline image from a list of Event objects.

    Events are sorted chronologically and spread evenly across the canvas.
    Returns the path to the saved PNG.
    """
    if output_path is None:
        slug = title.lower().replace(" ", "_")[:30]
        output_path = Path("output/images") / f"timeline_{slug}.png"

    accent = accent_color or PALETTE["accent_default"]
    accent_rgb = hex_to_rgb(accent)

    img, draw = new_image(DIMS["twitter"], PALETTE["background"])

    # Accent bars
    draw.rectangle([0, 0, _W, _ACCENT_BAR], fill=accent_rgb)
    draw.rectangle([0, _H - _ACCENT_BAR, _W, _H], fill=accent_rgb)

    # Title
    title_font = load_font(44, bold=True)
    draw.text(
        (_MARGIN, _ACCENT_BAR + 20),
        title,
        font=title_font,
        fill=hex_to_rgb(PALETTE["text_primary"]),
    )

    # Handle (top-right)
    handle_font = load_font(28)
    handle_w = (
        draw.textlength(handle, font=handle_font)
        if hasattr(draw, "textlength")
        else len(handle) * 16
    )
    draw.text(
        (_W - _MARGIN - int(handle_w), _ACCENT_BAR + 28),
        handle,
        font=handle_font,
        fill=hex_to_rgb(PALETTE["text_muted"]),
    )

    # Separator under title
    sep_y = _ACCENT_BAR + 86
    sep_rgb = hex_to_rgb(PALETTE["border"])
    draw.line([(_MARGIN, sep_y), (_W - _MARGIN, sep_y)], fill=sep_rgb, width=2)

    if not events:
        save_image(img, output_path)
        return output_path

    # Sort events chronologically
    sorted_events = sorted(events, key=lambda e: e.date)
    n = len(sorted_events)

    # Timeline spine
    spine_y = _H // 2 + 20
    spine_x_start = _MARGIN + 20
    spine_x_end = _W - _MARGIN - 20
    draw.line([(spine_x_start, spine_y), (spine_x_end, spine_y)], fill=accent_rgb, width=4)

    # Distribute event x-positions evenly
    if n == 1:
        xs = [(spine_x_start + spine_x_end) // 2]
    else:
        gap = (spine_x_end - spine_x_start) // (n - 1)
        xs = [spine_x_start + i * gap for i in range(n)]

    dot_radius = 10
    label_font = load_font(22, bold=False)
    date_font = load_font(20, bold=True)
    text_color = hex_to_rgb(PALETTE["text_secondary"])

    for i, (event, x) in enumerate(zip(sorted_events, xs)):
        # Node dot
        draw.ellipse(
            [x - dot_radius, spine_y - dot_radius, x + dot_radius, spine_y + dot_radius],
            fill=accent_rgb,
        )

        # Alternate labels above/below spine to avoid overlaps
        above = (i % 2 == 0)

        # Date label
        date_str = str(event.date)[:7]  # YYYY-MM
        date_w = (
            draw.textlength(date_str, font=date_font)
            if hasattr(draw, "textlength")
            else len(date_str) * 12
        )
        if above:
            # Date above the spine
            draw.text(
                (x - int(date_w) // 2, spine_y - dot_radius - 44),
                date_str,
                font=date_font,
                fill=accent_rgb,
            )
            # Title below date
            _draw_event_label(draw, event.title, x, spine_y - dot_radius - 88, label_font, text_color, above=True)
        else:
            # Date below the spine
            draw.text(
                (x - int(date_w) // 2, spine_y + dot_radius + 14),
                date_str,
                font=date_font,
                fill=accent_rgb,
            )
            # Title below date
            _draw_event_label(draw, event.title, x, spine_y + dot_radius + 52, label_font, text_color, above=False)

    return save_image(img, output_path)


def _draw_event_label(
    draw,
    title: str,
    cx: int,
    y: int,
    font,
    color: tuple,
    above: bool,
    max_chars: int = 18,
    max_lines: int = 2,
) -> None:
    """Draw a short event title centered at cx, stacked upward (above) or downward."""
    import textwrap
    lines = textwrap.wrap(title, width=max_chars)[:max_lines]
    line_h = 26
    if above:
        # Draw from bottom of block upward
        start_y = y - len(lines) * line_h
    else:
        start_y = y

    for j, line in enumerate(lines):
        w = draw.textlength(line, font=font) if hasattr(draw, "textlength") else len(line) * 13
        draw.text((cx - int(w) // 2, start_y + j * line_h), line, font=font, fill=color)
