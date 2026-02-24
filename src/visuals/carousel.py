"""
Instagram carousel generator.

Takes a ContentDraft (with formatted carousel text from the Phase 1 formatter)
and renders it as a sequence of 1080×1080 PNG slides.

Slide layout:
  ┌──────────────────────────────┐
  │ ████ accent bar (8px)        │  ← institution/type color
  │                              │
  │  [slide number]  [tag]       │  ← top-left: "1/5", top-right: tag
  │                              │
  │  TITLE (bold, large)         │  ← main heading
  │                              │
  │  Body text (wrapped)         │  ← content paragraphs
  │                              │
  │  ─────────────────────────   │  ← separator
  │  @anticorrupt  [source]      │  ← footer
  │ ████ accent bar (8px)        │
  └──────────────────────────────┘
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.visuals.renderer import (
    DIMS,
    PALETTE,
    TextBlock,
    draw_accent_bar,
    draw_text_block,
    institution_color,
    load_font,
    new_image,
    save_image,
)

# ---------------------------------------------------------------------------
# Slide data model
# ---------------------------------------------------------------------------

@dataclass
class Slide:
    """Data for a single carousel slide."""
    index: int           # 1-based
    total: int           # total number of slides
    title: str
    body: str
    accent_color: str
    tag: str = ""
    source: str = ""
    handle: str = "@anticorrupt"


# ---------------------------------------------------------------------------
# Parser: text → slides
# ---------------------------------------------------------------------------

def parse_carousel_text(formatted_text: str) -> list[Slide]:
    """
    Parse the output of Phase 1's InstagramFormatter into Slide objects.

    Expected format from formatter.py:
        === CAROUSEL (N slides) ===

        --- Slide 1 ---
        📌 Title here

        Body text here

        --- Slide 2 ---
        ...

        --- Hashtags ---
        #tag1 #tag2
    """
    slides: list[Slide] = []

    # Extract total count
    total_match = re.search(r"CAROUSEL \((\d+) slides?\)", formatted_text)
    total = int(total_match.group(1)) if total_match else 1

    # Strip the hashtags/footer section before splitting
    text_body = re.split(r"--- Hashtags ---", formatted_text)[0]

    # Split by slide separator
    slide_blocks = re.split(r"--- Slide \d+ ---", text_body)
    # Remove preamble (contains CAROUSEL header)
    slide_blocks = [b.strip() for b in slide_blocks if b.strip() and "CAROUSEL" not in b]

    for i, block in enumerate(slide_blocks, start=1):
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        # First non-empty line is the title (strip emoji markers like 📌)
        title_raw = lines[0]
        title = re.sub(r"^[^\w]+", "", title_raw).strip()
        body = "\n".join(lines[1:]).strip()
        slides.append(Slide(index=i, total=total, title=title, body=body, accent_color=PALETTE["accent_default"]))

    return slides


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class CarouselRenderer:
    """
    Render a list of Slide objects to PNG files.

    Usage:
        renderer = CarouselRenderer(output_dir=Path("output/images/my_carousel"))
        renderer.set_accent(institution_color("judicial"))
        paths = renderer.render(slides)
    """

    SLIDE_DIMS = DIMS["instagram_square"]
    MARGIN = 64
    ACCENT_BAR = 10

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        accent_color: Optional[str] = None,
        handle: str = "@anticorrupt",
    ):
        self._output_dir = output_dir or Path("output/images")
        self._accent_color = accent_color or PALETTE["accent_default"]
        self._handle = handle

    def set_accent(self, color: str) -> None:
        self._accent_color = color

    # ------------------------------------------------------------------
    # Render single slide
    # ------------------------------------------------------------------

    def _render_slide(self, slide: Slide) -> "Image":  # type: ignore[name-defined]
        from PIL import Image  # local import to avoid circular at module level
        img, draw = new_image(self.SLIDE_DIMS, PALETTE["background"])
        W, H = self.SLIDE_DIMS.size
        M = self.MARGIN
        bar = self.ACCENT_BAR
        accent_rgb = self._parse_color(slide.accent_color or self._accent_color)

        # Top accent bar
        draw.rectangle([0, 0, W, bar], fill=accent_rgb)

        # Bottom accent bar
        draw.rectangle([0, H - bar, W, H], fill=accent_rgb)

        # Slide counter: "1 / 5"
        counter_font = load_font(28)
        draw.text(
            (M, bar + 20),
            f"{slide.index} / {slide.total}",
            font=counter_font,
            fill=self._parse_color(PALETTE["text_muted"]),
        )

        # Tag (top-right)
        if slide.tag:
            tag_font = load_font(24)
            tag_text = f"#{slide.tag}" if not slide.tag.startswith("#") else slide.tag
            tag_w = draw.textlength(tag_text, font=tag_font) if hasattr(draw, "textlength") else len(tag_text) * 14
            draw.text(
                (W - M - int(tag_w), bar + 20),
                tag_text,
                font=tag_font,
                fill=accent_rgb,
            )

        # Title
        title_y = bar + 80
        title_block = TextBlock(
            text=slide.title,
            x=M,
            y=title_y,
            font_size=52,
            bold=True,
            color=PALETTE["text_primary"],
            max_width=W - 2 * M,
        )
        body_start_y = draw_text_block(draw, title_block) + 24

        # Separator line under title
        sep_color = self._parse_color(PALETTE["border"])
        draw.line([(M, body_start_y), (W - M, body_start_y)], fill=sep_color, width=2)
        body_start_y += 24

        # Body text
        if slide.body:
            body_block = TextBlock(
                text=slide.body,
                x=M,
                y=body_start_y,
                font_size=34,
                bold=False,
                color=PALETTE["text_secondary"],
                max_width=W - 2 * M,
            )
            draw_text_block(draw, body_block)

        # Footer
        footer_y = H - bar - 60
        draw.line([(M, footer_y - 16), (W - M, footer_y - 16)], fill=sep_color, width=1)
        footer_font = load_font(26)
        draw.text(
            (M, footer_y),
            slide.handle if slide.handle else self._handle,
            font=footer_font,
            fill=self._parse_color(PALETTE["text_muted"]),
        )
        if slide.source:
            src_w = draw.textlength(slide.source, font=footer_font) if hasattr(draw, "textlength") else len(slide.source) * 15
            draw.text(
                (W - M - int(src_w), footer_y),
                slide.source,
                font=footer_font,
                fill=self._parse_color(PALETTE["text_muted"]),
            )

        return img

    # ------------------------------------------------------------------
    # Render full carousel
    # ------------------------------------------------------------------

    def render(self, slides: list[Slide], draft_id: str = "carousel") -> list[Path]:
        """
        Render all slides and save to disk.
        Returns list of absolute paths to the generated PNG files.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for slide in slides:
            slide.accent_color = slide.accent_color or self._accent_color
            slide.handle = slide.handle or self._handle
            img = self._render_slide(slide)
            filename = f"{draft_id}_slide_{slide.index:02d}.png"
            path = save_image(img, self._output_dir / filename)
            paths.append(path)
        return paths

    @staticmethod
    def _parse_color(hex_color: str) -> tuple[int, int, int]:
        from src.visuals.renderer import hex_to_rgb
        return hex_to_rgb(hex_color)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def render_carousel_from_draft(
    formatted_text: str,
    draft_id: str,
    institution_type: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> list[Path]:
    """
    High-level helper: parse formatted carousel text → render slides → return paths.

    Args:
        formatted_text: Output of InstagramFormatter.format() from Phase 1.
        draft_id:        Used as filename prefix.
        institution_type: e.g. "judicial", "legislative" — sets accent color.
        output_dir:      Where to save PNGs. Defaults to output/images/<draft_id>/.
    """
    slides = parse_carousel_text(formatted_text)
    if not slides:
        return []

    out = output_dir or Path("output/images") / draft_id
    accent = institution_color(institution_type)

    renderer = CarouselRenderer(output_dir=out, accent_color=accent)
    return renderer.render(slides, draft_id=draft_id)
