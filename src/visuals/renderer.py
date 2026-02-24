"""
Base visual renderer — shared colors, fonts, dimensions, and Pillow utilities.

All visual generators (carousel, profile, timeline, network, diagram) inherit
from or compose with this module. Nothing here is platform-specific.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

# Institution type → accent color (matches PROJECT_PLAN.md §6.3)
INSTITUTION_COLORS: dict[str, str] = {
    "judicial": "#1A365D",      # Deep Blue
    "legislative": "#276749",   # Green
    "executive": "#975A16",     # Gold/Yellow
    "independent": "#553C9A",   # Purple
    "military": "#2D3748",      # Dark Gray
    "default": "#4A5568",       # Slate
}

# Full palette (name → hex)
PALETTE = {
    "background": "#FAFAFA",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "text_primary": "#1A202C",
    "text_secondary": "#4A5568",
    "text_muted": "#718096",
    "accent_judiciary": "#1A365D",
    "accent_legislature": "#276749",
    "accent_executive": "#975A16",
    "accent_independent": "#553C9A",
    "accent_military": "#2D3748",
    "accent_default": "#4A5568",
    "white": "#FFFFFF",
    "black": "#000000",
    "success": "#276749",
    "warning": "#975A16",
    "danger": "#9B2C2C",
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def institution_color(inst_type: Optional[str]) -> str:
    """Return the hex accent color for a given institution type string."""
    if inst_type is None:
        return INSTITUTION_COLORS["default"]
    key = inst_type.lower()
    # Handle common aliases
    for k in ("judicial", "legislative", "executive", "independent", "military"):
        if k in key:
            return INSTITUTION_COLORS[k]
    return INSTITUTION_COLORS["default"]


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

@dataclass
class Dimensions:
    width: int
    height: int

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def center(self) -> tuple[int, int]:
        return (self.width // 2, self.height // 2)


DIMS = {
    "instagram_square": Dimensions(1080, 1080),
    "instagram_story": Dimensions(1080, 1920),
    "twitter": Dimensions(1200, 675),
    "thumbnail": Dimensions(540, 540),
}


# ---------------------------------------------------------------------------
# Font management
# ---------------------------------------------------------------------------

# Try to load system fonts; fall back to PIL default if not found.
# On macOS: /System/Library/Fonts/  or  /Library/Fonts/
# On Linux: /usr/share/fonts/
_FONT_SEARCH_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_FONT_BOLD_SEARCH_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _find_font(paths: list[str]) -> Optional[str]:
    for p in paths:
        if Path(p).exists():
            return p
    return None


_REGULAR_FONT_PATH = _find_font(_FONT_SEARCH_PATHS)
_BOLD_FONT_PATH = _find_font(_FONT_BOLD_SEARCH_PATHS)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at the given size. Falls back to PIL default if no TTF found."""
    path = _BOLD_FONT_PATH if bold else _REGULAR_FONT_PATH
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing utilities
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    """A text region to render onto an image."""
    text: str
    x: int
    y: int
    font_size: int = 32
    bold: bool = False
    color: str = "#1A202C"
    max_width: int = 900          # pixels — text wraps if wider
    line_spacing: float = 1.4


def draw_text_block(draw: ImageDraw.ImageDraw, block: TextBlock) -> int:
    """
    Draw a wrapped text block on an ImageDraw canvas.
    Returns the y-coordinate after the last line (useful for stacking blocks).
    """
    font = load_font(block.font_size, bold=block.bold)
    color = hex_to_rgb(block.color)

    # Estimate chars per line based on font size (rough but works for monospace fallback)
    # For TTF fonts, we measure actual pixel width per character
    if hasattr(font, "getlength"):
        avg_char_width = font.getlength("M")
    else:
        avg_char_width = block.font_size * 0.6  # rough estimate

    chars_per_line = max(10, int(block.max_width / avg_char_width))
    lines = []
    for paragraph in block.text.split("\n"):
        if paragraph.strip():
            wrapped = textwrap.wrap(paragraph, width=chars_per_line)
            lines.extend(wrapped)
        else:
            lines.append("")  # preserve blank lines

    line_height = int(block.font_size * block.line_spacing)
    y = block.y
    for line in lines:
        draw.text((block.x, y), line, font=font, fill=color)
        y += line_height

    return y


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int = 16,
    fill: Optional[str] = None,
    outline: Optional[str] = None,
    outline_width: int = 2,
) -> None:
    """Draw a rounded rectangle on an ImageDraw canvas."""
    fill_rgb = hex_to_rgb(fill) if fill else None
    outline_rgb = hex_to_rgb(outline) if outline else None
    draw.rounded_rectangle(xy, radius=radius, fill=fill_rgb, outline=outline_rgb, width=outline_width)


def draw_accent_bar(
    draw: ImageDraw.ImageDraw,
    width: int,
    color: str,
    x: int = 0,
    y: int = 0,
    bar_height: int = 8,
) -> None:
    """Draw a full-width colored accent bar (used at top/bottom of slides)."""
    rgb = hex_to_rgb(color)
    draw.rectangle([x, y, x + width, y + bar_height], fill=rgb)


# ---------------------------------------------------------------------------
# Base image factory
# ---------------------------------------------------------------------------

def new_image(
    dims: Dimensions = DIMS["instagram_square"],
    background: str = PALETTE["background"],
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create a blank PIL Image with ImageDraw, ready to draw on."""
    img = Image.new("RGB", dims.size, hex_to_rgb(background))
    draw = ImageDraw.Draw(img)
    return img, draw


def save_image(img: Image.Image, path: Union[str, Path], quality: int = 95) -> Path:
    """Save an Image to disk as PNG. Creates parent directories if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(p), format="PNG", optimize=True)
    return p
