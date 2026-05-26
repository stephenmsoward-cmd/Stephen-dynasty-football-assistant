"""Generate Open Graph / Twitter card images.

Outputs site/og.png — a 1200×630 image with Dynasty Tools branding. Each
HTML page references this image via og:image meta tags and overrides
og:title and og:description per page for context.

Per-league images could be a future enhancement; for now one shared image
keeps the build fast and the design consistent.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
BG = (15, 17, 21)            # --bg
PANEL = (24, 27, 34)         # --surface
PANEL_2 = (33, 37, 46)       # --surface-2
TEXT = (230, 232, 237)       # --text
MUTED = (139, 145, 159)      # --muted
ACCENT = (122, 162, 247)     # --accent
GOOD = (158, 206, 106)       # --good
WARN = (224, 175, 104)       # --warn


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try a few common font paths; fall back to PIL's default if none work."""
    candidates_bold = [
        "/System/Library/Fonts/Helvetica.ttc",         # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    candidates_regular = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    paths = candidates_bold if bold else candidates_regular
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def make_og_image(output_path: Path) -> None:
    """Generate the shared OG image."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Left accent stripe.
    draw.rectangle([0, 0, 12, HEIGHT], fill=ACCENT)

    # Subtle "DYNASTY TOOLS" eyebrow text up top.
    draw.text(
        (60, 60),
        "DYNASTY TOOLS",
        font=_font(28, bold=True),
        fill=ACCENT,
    )

    # Main headline.
    draw.text(
        (60, 130),
        "Dynasty fantasy football,",
        font=_font(72, bold=True),
        fill=TEXT,
    )
    draw.text(
        (60, 220),
        "made legible.",
        font=_font(72, bold=True),
        fill=TEXT,
    )

    # Subtitle / tagline.
    draw.text(
        (60, 340),
        "Best-ball projections · Trade finder · Waiver wire · Draft board",
        font=_font(28),
        fill=MUTED,
    )

    # Three feature pills along the bottom.
    pills = [
        ("Dynasty + Win-Now", ACCENT),
        ("Pick-aware trades", WARN),
        ("Power rankings + compare", GOOD),
    ]
    x = 60
    y = 470
    for label, color in pills:
        text_w = draw.textlength(label, font=_font(24, bold=True))
        pad_x = 22
        pill_w = int(text_w + pad_x * 2)
        draw.rounded_rectangle([x, y, x + pill_w, y + 56], radius=12, fill=PANEL_2)
        draw.rectangle([x, y, x + 4, y + 56], fill=color)
        draw.text((x + pad_x, y + 12), label, font=_font(24, bold=True), fill=TEXT)
        x += pill_w + 20

    # Footer URL.
    draw.text(
        (60, HEIGHT - 70),
        "github.com/stephenmsoward-cmd/Stephen-dynasty-football-assistant",
        font=_font(20),
        fill=MUTED,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
