"""Generate the ConvertAll app icon.

Run from the project root:  python tools/make_icon.py

Draws the mark at 1024px, saves assets/icon.png, then hands it to ConvertAll's
own ICO pipeline to produce the multi-resolution assets/icon.ico.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from convertall.core.images import convert_image  # noqa: E402
from convertall.theme import DARK  # noqa: E402

SIZE = 1024


def draw_arrow(draw, y, direction, colour, size=SIZE):
    """A horizontal arrow: a bar plus a triangular head."""
    unit = size / 32
    left, right = 7 * unit, 25 * unit
    thickness = 2.6 * unit
    head = 4.2 * unit

    if direction > 0:
        draw.rounded_rectangle(
            [left, y - thickness / 2, right - head, y + thickness / 2],
            radius=thickness / 2,
            fill=colour,
        )
        draw.polygon(
            [(right, y), (right - head, y - head * 0.78), (right - head, y + head * 0.78)],
            fill=colour,
        )
    else:
        draw.rounded_rectangle(
            [left + head, y - thickness / 2, right, y + thickness / 2],
            radius=thickness / 2,
            fill=colour,
        )
        draw.polygon(
            [(left, y), (left + head, y - head * 0.78), (left + head, y + head * 0.78)],
            fill=colour,
        )


def build() -> Path:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded amber tile, matching the accent colour used across the app.
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=SIZE * 0.22, fill=DARK.accent)
    # Inset dark panel so the arrows read at 16px.
    inset = SIZE * 0.11
    draw.rounded_rectangle(
        [inset, inset, SIZE - inset, SIZE - inset],
        radius=SIZE * 0.15,
        fill=DARK.bg,
    )

    draw_arrow(draw, SIZE * 0.40, +1, DARK.accent)
    draw_arrow(draw, SIZE * 0.60, -1, DARK.text)

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    png = assets / "icon.png"
    img.save(png)

    result = convert_image(png, assets, target="ico", ico_sizes=(16, 24, 32, 48, 64, 128, 256))
    final = assets / "icon.ico"
    if result.output != final:
        final.unlink(missing_ok=True)
        result.output.replace(final)

    print(f"Wrote {png.relative_to(ROOT)} and {final.relative_to(ROOT)}")
    return final


if __name__ == "__main__":
    build()
