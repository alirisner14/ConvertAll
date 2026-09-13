"""Tests for splitting a sprite into labelled parts.

Synthetic sprites throughout - no dependency on anyone's artwork, and no
display needed.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from convertall.core.parts import METHODS, export_parts, split_into_parts

pytest.importorskip("cv2")

RED = (220, 60, 60)
BLUE = (60, 90, 220)
CANVAS = 200


@pytest.fixture
def sprite(tmp_path):
    """Two touching blocks on transparency: one internal seam, one silhouette."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    px = img.load()
    for y in range(40, 160):
        for x in range(40, 100):
            px[x, y] = (*RED, 255)
        for x in range(100, 160):
            px[x, y] = (*BLUE, 255)
    path = tmp_path / "sprite.png"
    img.save(path)
    return path


@pytest.fixture
def strokes(tmp_path):
    """A dab inside each block, in its own mask colour."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    px = img.load()
    for y in range(90, 110):
        for x in range(60, 80):
            px[x, y] = (255, 0, 0, 255)
        for x in range(120, 140):
            px[x, y] = (0, 0, 255, 255)
    path = tmp_path / "mask.png"
    img.save(path)
    return path


@pytest.fixture
def cut_line(tmp_path):
    """A line straight down the seam."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    px = img.load()
    for y in range(30, 170):
        for x in range(98, 103):
            px[x, y] = (0, 0, 0, 255)
    path = tmp_path / "cut.png"
    img.save(path)
    return path


NAMES = {"#ff0000": "left", "#0000ff": "right"}


def test_every_method_is_documented():
    assert set(METHODS) == {"grow", "mask", "cut"}
    assert all(text for text in METHODS.values())


def test_unknown_method_is_rejected(sprite, strokes):
    with pytest.raises(ValueError, match="Unknown method"):
        split_into_parts(sprite, strokes, method="magic")


def test_mask_of_the_wrong_size_is_rejected(sprite, tmp_path):
    small = tmp_path / "small.png"
    Image.new("RGBA", (50, 50)).save(small)
    with pytest.raises(RuntimeError, match="must match"):
        split_into_parts(sprite, small)


def test_an_empty_mask_is_rejected(sprite, tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0)).save(blank)
    with pytest.raises(RuntimeError, match="nothing was painted"):
        split_into_parts(sprite, blank)


def test_mask_method_uses_exactly_what_was_painted(sprite, strokes):
    parts = split_into_parts(sprite, strokes, method="mask", extend_px=0, names=NAMES)
    assert {p.label for p in parts} == {"left", "right"}
    for part in parts:
        assert part.pixels == 20 * 20, "the mask method must not grow the stroke"


def test_grow_method_expands_to_the_artwork(sprite, strokes):
    parts = split_into_parts(sprite, strokes, method="grow", extend_px=0, names=NAMES)
    assert {p.label for p in parts} == {"left", "right"}
    for part in parts:
        assert part.pixels > 20 * 20 * 4, "grow should fill its block, not sit on the stroke"


def test_grow_separates_blocks_at_the_seam(sprite, strokes):
    parts = {p.label: p for p in split_into_parts(sprite, strokes, "grow", 0, NAMES)}
    left = parts["left"].rgba[:, :, 3] > 0
    right = parts["right"].rgba[:, :, 3] > 0
    assert not (left & right).any(), "parts must not overlap before extension"
    # Each part should sit on its own side of x=100.
    assert np.nonzero(left)[1].mean() < 100 < np.nonzero(right)[1].mean()


def test_cut_method_splits_on_the_drawn_line(sprite, cut_line):
    parts = split_into_parts(sprite, cut_line, method="cut", extend_px=0)
    assert len(parts) == 2


def test_parts_stay_on_the_full_canvas_and_in_register(sprite, strokes):
    parts = split_into_parts(sprite, strokes, "grow", 0, NAMES)
    for part in parts:
        assert part.rgba.shape[:2] == (CANVAS, CANVAS)


def test_extension_never_grows_the_silhouette(sprite, strokes):
    """The subtle one. Extending must fill under a neighbour, not fatten the outline."""
    original = np.array(Image.open(sprite).convert("RGBA"))[:, :, 3] > 128

    parts = split_into_parts(sprite, strokes, "grow", extend_px=25, names=NAMES)
    union = np.zeros_like(original)
    for part in parts:
        union |= part.rgba[:, :, 3] > 0

    outside = union & ~original
    assert not outside.any(), (
        f"{int(outside.sum())} extended pixels landed outside the sprite - "
        "the extension escaped the silhouette"
    )


def test_extension_actually_adds_overlap(sprite, strokes):
    parts = split_into_parts(sprite, strokes, "grow", extend_px=25, names=NAMES)
    assert all(p.extended_pixels > 0 for p in parts)

    plain = {p.label: p for p in split_into_parts(sprite, strokes, "grow", 0, NAMES)}
    for part in parts:
        grew = (part.rgba[:, :, 3] > 0).sum()
        flat = (plain[part.label].rgba[:, :, 3] > 0).sum()
        assert grew > flat, f"{part.label} did not gain any overlap"


def test_extension_copies_neighbouring_colour_not_black(sprite, strokes):
    """Replicated pixels must carry the edge colour, not arrive as holes."""
    parts = {p.label: p for p in split_into_parts(sprite, strokes, "grow", 25, NAMES)}
    left = parts["left"]
    filled = left.rgba[:, :, 3] > 0
    colours = left.rgba[filled][:, :3]
    assert not (colours == 0).all(axis=1).any(), "extension produced black pixels"


def test_png_export_writes_a_file_per_part_plus_a_manifest(sprite, strokes, tmp_path):
    parts = split_into_parts(sprite, strokes, "grow", 10, NAMES)
    result = export_parts(sprite, parts, tmp_path / "out", fmt="png")

    written = [result.output, *result.extra_outputs]
    pngs = [p for p in written if p.suffix == ".png"]
    manifests = [p for p in written if p.suffix == ".json"]
    assert len(pngs) == len(parts)
    assert len(manifests) == 1

    data = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert data["canvas"] == {"width": CANVAS, "height": CANVAS}
    assert {p["label"] for p in data["parts"]} == {"left", "right"}
    assert all("bbox" in p and "centroid" in p for p in data["parts"])


def test_svg_export_names_every_group(sprite, strokes, tmp_path):
    parts = split_into_parts(sprite, strokes, "grow", 10, NAMES)
    result = export_parts(sprite, parts, tmp_path / "out", fmt="svg")

    svg = next(p for p in [result.output, *result.extra_outputs] if p.suffix == ".svg")
    text = svg.read_text(encoding="utf-8")
    for label in ("left", "right"):
        assert f'<g id="{label}"' in text, f"{label} has no named group"
    assert "<image" not in text and "base64" not in text, "parts must be vectors"


def test_unsupported_export_format_is_rejected(sprite, strokes, tmp_path):
    parts = split_into_parts(sprite, strokes, "grow", 0, NAMES)
    with pytest.raises(ValueError, match="Unsupported format"):
        export_parts(sprite, parts, tmp_path / "out", fmt="gif")
