"""Tracing a tile that still tiles.

A pattern tile looks fine on its own and wrong only when it repeats, so these
tests check the thing that actually breaks: whether geometry crossing the tile
edge was cut at the boundary (continuous when repeated) or fitted to it
(two independently smoothed curves that will not line up).
"""

from __future__ import annotations

import re

import numpy as np
import pytest
from lxml import etree
from PIL import Image

from convertall.core.vectorize import (
    repeat_preview,
    trace_image,
    wrap_edges,
    wrap_pad_for,
)

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def tile(tmp_path):
    """A tile with a blob deliberately straddling the left/right edge."""
    img = Image.new("RGB", (200, 200), (250, 245, 230))
    pixels = img.load()
    for y in range(200):
        for x in range(200):
            # A disc centred on the seam, so half of it wraps around.
            if (min(x, 200 - x)) ** 2 + (y - 100) ** 2 < 45**2:
                pixels[x, y] = (40, 120, 90)
            if (x - 100) ** 2 + (y - 40) ** 2 < 25**2:
                pixels[x, y] = (200, 70, 60)
    path = tmp_path / "pattern tile.png"
    img.save(path)
    return path


def _coords(svg_path):
    root = etree.parse(str(svg_path)).getroot()
    numbers = []
    for element in root.iter(f"{SVG}path"):
        numbers += [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", element.get("d", ""))]
    return numbers[0::2], numbers[1::2]  # x, y


# --- the wrap itself --------------------------------------------------------- #


def test_wrap_puts_the_opposite_edge_in_the_margin():
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4)
    img = Image.fromarray(np.dstack([arr] * 4), "RGBA")
    padded = np.asarray(wrap_edges(img, 2))
    # The left margin must be the tile's right-hand columns, in order.
    assert padded[2:6, 0, 0].tolist() == arr[:, 2].tolist()
    assert padded[2:6, 1, 0].tolist() == arr[:, 3].tolist()


def test_wrap_is_proportional_but_never_trivial():
    assert wrap_pad_for((1000, 1000)) == 100
    assert wrap_pad_for((20, 20)) >= 8  # a tiny tile still gets usable margin


# --- what lands in the SVG --------------------------------------------------- #


def test_a_plain_trace_stops_at_the_tile_edge(tile, tmp_path):
    result = trace_image(tile, tmp_path / "plain", engine="color", detail="low", seamless=False)
    xs, ys = _coords(result.output)
    assert min(xs) >= 0 and min(ys) >= 0
    root = etree.parse(str(result.output)).getroot()
    assert root.find(f".//{SVG}clipPath") is None


def test_a_seamless_trace_runs_through_the_edge_and_is_clipped(tile, tmp_path):
    """The point of the exercise: geometry continues past the boundary.

    If every coordinate stopped inside the tile, Potrace would have closed each
    shape against the border - which is exactly the case that leaves a seam.
    """
    result = trace_image(tile, tmp_path / "seam", engine="color", detail="low", seamless=True)
    root = etree.parse(str(result.output)).getroot()

    clip = root.find(f".//{SVG}clipPath")
    assert clip is not None, "without a clip the padding would show in the output"
    rect = clip.find(f"{SVG}rect")
    assert (rect.get("width"), rect.get("height")) == ("200", "200")

    group = root.find(f".//{SVG}g[@clip-path]")
    pad = wrap_pad_for((200, 200))
    assert group.get("transform") == f"translate({-pad} {-pad})"

    xs, _ = _coords(result.output)
    assert min(xs) < pad, "no geometry crossed the seam - the wrap did nothing"
    assert max(xs) > 200 + pad * 0.5


def test_the_tile_keeps_its_own_size(tile, tmp_path):
    """The padding must not leak into the viewBox, or the repeat spacing shifts."""
    result = trace_image(tile, tmp_path / "out", engine="color", detail="low", seamless=True)
    root = etree.parse(str(result.output)).getroot()
    assert root.get("viewBox") == "0 0 200 200"
    assert (root.get("width"), root.get("height")) == ("200", "200")


def test_mono_tiles_seamlessly_too(tile, tmp_path):
    result = trace_image(tile, tmp_path / "mono", engine="mono", detail="low", seamless=True)
    root = etree.parse(str(result.output)).getroot()
    assert root.find(f".//{SVG}clipPath") is not None


# --- recolouring ------------------------------------------------------------- #


def test_each_colour_is_a_named_group_carrying_the_fill(tile, tmp_path):
    result = trace_image(tile, tmp_path / "out", engine="color", detail="low", colors=4)
    root = etree.parse(str(result.output)).getroot()
    groups = root.findall(f".//{SVG}g")
    assert len(groups) >= 2
    for n, group in enumerate(groups, start=1):
        assert group.get("id") == f"colour-{n}"
        assert group.get("fill", "").startswith("#")
        # The path must not carry its own fill, or the group's is ignored.
        assert group.find(f"{SVG}path").get("fill") is None


def test_the_colours_control_changes_how_many_layers_there_are(tile, tmp_path):
    few = trace_image(tile, tmp_path / "few", engine="color", detail="low", colors=2)
    many = trace_image(tile, tmp_path / "many", engine="color", detail="low", colors=12)
    count = lambda r: len(etree.parse(str(r.output)).getroot().findall(f".//{SVG}g"))  # noqa: E731
    assert count(few) < count(many)


# --- the repeat preview ------------------------------------------------------- #


def test_the_preview_tiles_the_result(tile, tmp_path):
    result = trace_image(
        tile, tmp_path / "out", engine="color", detail="low", seamless=True, preview=True
    )
    assert result.extra_outputs, "asked for a preview and got none"
    preview = result.extra_outputs[0]
    root = etree.parse(str(preview)).getroot()
    images = root.findall(f".//{SVG}image")
    assert len(images) == 9
    assert root.get("viewBox") == "0 0 600 600"
    # Referenced, not copied, so re-tracing updates the preview as well.
    assert images[0].get("href") == result.output.name


def test_no_preview_unless_asked(tile, tmp_path):
    result = trace_image(tile, tmp_path / "out", engine="color", detail="low", seamless=True)
    assert result.extra_outputs == []


def test_preview_reads_the_tile_size_from_the_svg(tile, tmp_path):
    result = trace_image(tile, tmp_path / "out", engine="color", detail="low")
    dst = repeat_preview(result.output, tmp_path / "check.svg", times=2)
    root = etree.parse(str(dst)).getroot()
    assert len(root.findall(f".//{SVG}image")) == 4
    assert root.get("viewBox") == "0 0 400 400"
