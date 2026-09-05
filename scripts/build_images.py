"""Generate the share card and the favicon set.

Kept as a script rather than committed binaries with no history, so the day the
colours change these regenerate instead of drifting out of sync with the CSS.

    python scripts/build_images.py
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

GREEN_DARK = (20, 86, 58)
GREEN = (31, 122, 76)
LEAF = (127, 216, 168)
BLUE = (98, 185, 216)
CREAM = (246, 249, 245)
WHITE = (255, 255, 255)

FONT_DIR = "/usr/share/fonts/truetype/google-fonts"
FALLBACK = "/usr/share/fonts/truetype/dejavu"


def font(name: str, size: int):
    for path in (os.path.join(FONT_DIR, name),
                 os.path.join(FALLBACK, "DejaVuSans-Bold.ttf"),
                 os.path.join(FALLBACK, "DejaVuSans.ttf")):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_mark(img: Image.Image, x: int, y: int, size: int) -> None:
    """The same house and leaf as the SVG in the masthead, drawn to pixels."""
    d = ImageDraw.Draw(img)
    s = size / 40.0

    def p(px, py):
        return (x + px * s, y + py * s)

    # Roof and walls, one closed shape.
    d.polygon([p(20, 3), p(33, 15), p(33, 35), p(7, 35), p(7, 15)], fill=BLUE)
    # The leaf.
    d.polygon(
        [p(20, 10), p(24, 14), p(26, 20), p(23, 25), p(20, 26),
         p(17, 25), p(14, 20), p(16, 14)],
        fill=LEAF,
    )
    r = 2.4 * s
    cx, cy = p(20, 30)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)


def share_card() -> str:
    """1200x630. Slack, LinkedIn, iMessage and Twitter all crop to about this,
    so everything important stays well inside the middle."""
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), GREEN_DARK)
    d = ImageDraw.Draw(img)

    # A soft band so it is not a flat rectangle.
    d.ellipse([-260, 300, 620, 1180], fill=GREEN)
    d.rectangle([0, h - 16, w, h], fill=LEAF)

    draw_mark(img, 84, 96, 150)

    title = font("Poppins-Bold.ttf", 82)
    sub = font("Poppins-Medium.ttf", 38)
    small = font("Poppins-Medium.ttf", 28)

    d.text((84, 276), "Kid Events in", font=title, fill=WHITE)
    d.text((84, 366), "Ann Arbor", font=title, fill=LEAF)
    d.text((88, 478),
           "Storytimes, playgroups and festivals,",
           font=sub, fill=(214, 236, 224))
    d.text((88, 522), "all on one page you can filter.", font=sub, fill=(214, 236, 224))
    d.text((88, 560), "shinabarger.github.io/kid-events-in-ann-arbor",
           font=small, fill=(150, 200, 176))

    path = os.path.join(OUT, "og-cover.png")
    img.save(path, "PNG", optimize=True)
    return path


def icon(size: int, pad_ratio: float = 0.13, bg=GREEN_DARK, radius_ratio=0.22) -> Image.Image:
    img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    big = size * 4
    d.rounded_rectangle([0, 0, big, big], radius=int(big * radius_ratio), fill=bg)
    pad = int(big * pad_ratio)
    draw_mark(img, pad, pad, big - pad * 2)
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    written = [share_card()]

    for size, name in [(16, "favicon-16.png"), (32, "favicon-32.png"),
                       (192, "icon-192.png"), (512, "icon-512.png")]:
        path = os.path.join(OUT, name)
        icon(size).save(path, "PNG", optimize=True)
        written.append(path)

    # Apple wants a square with no transparency; it rounds the corners itself.
    apple = Image.new("RGB", (180, 180), GREEN_DARK)
    apple.paste(icon(180, pad_ratio=0.16, radius_ratio=0).convert("RGB"), (0, 0))
    path = os.path.join(OUT, "apple-touch-icon.png")
    apple.save(path, "PNG", optimize=True)
    written.append(path)

    # The multi-size .ico that older browsers and Windows still ask for.
    path = os.path.join(OUT, "favicon.ico")
    icon(64).save(path, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    written.append(path)

    for p in written:
        print(f"{os.path.relpath(p, ROOT)}  {os.path.getsize(p):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
