"""Raster -> vector auto-tracing, built on Potrace.

Two engines, one dependency:

* **mono**  - classic Potrace. The image is thresholded to black and white and
  traced into a single filled path. The crispest possible result for line art,
  silhouettes and stencils.
* **color** - the image is posterised to a small palette, then each colour is
  traced as its own layer and the layers are stacked back up in area order.
  This is how colour auto-tracers work under the hood, and doing it here keeps
  the whole feature on one well-understood, pure-Python engine.

Both engines share `_trace_mask`, so curve quality is identical between them.

Seamless tiles get an extra step. Tracing a tile on its own lets Potrace close
each shape against the tile border, and the two borders are fitted
independently - so curve smoothing and anti-aliased edges leave the left and
right halves of a shape slightly different, and the seam shows when the tile
repeats. `seamless=True` pads the tile with its own opposite edges, traces
that, and clips back to the tile rectangle, so geometry crossing the seam is
one continuous curve that was cut at the boundary rather than two curves that
have to agree.
"""

from __future__ import annotations

from pathlib import Path

from .common import TaskResult, ensure_dir, size_of, unique_path

ENGINES = {
    "color": "Colour artwork (posterise + Potrace)",
    "mono": "Black & white line art (Potrace)",
}

# detail -> (palette colours, speckle filter, longest traced edge in px)
DETAIL = {
    "high": (16, 2, 2000),
    "medium": (8, 4, 1400),
    "low": (4, 10, 1000),
}
DETAIL_LABELS = {
    "high": "High detail",
    "medium": "Balanced",
    "low": "Simplified",
}

# How many colours the Colours control offers. Flat Procreate artwork is
# usually happy between 4 and 12; the ceiling is for photographic sources.
MIN_COLORS, MAX_COLORS = 2, 32

# Colour layers smaller than this share of the image are dropped as noise.
_MIN_LAYER_SHARE = 0.0008

# How much of the tile to wrap around the edges before a seamless trace. Only
# needs to exceed the reach of Potrace's curve fitting; 10% is generous and
# costs roughly 40% more geometry before the clip discards it.
_WRAP_SHARE = 0.10
_MIN_WRAP_PX = 8


def _require():
    try:
        import numpy as np
        import potrace
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Tracing needs Potrace - run: pip install potracer numpy") from exc
    return np, potrace


def _xy(point) -> tuple[float, float]:
    """potracer Points expose .x/.y; be forgiving about tuple-likes too."""
    x = getattr(point, "x", None)
    if x is not None:
        return float(x), float(point.y)
    return float(point[0]), float(point[1])


def _trace_mask(mask, turdsize: int) -> str:
    """Trace a boolean mask (True = filled) into SVG path data."""
    _, potrace = _require()

    # potracer's Bitmap inverts whatever it is handed, so pass the negative to
    # get the region we actually want filled.
    path = potrace.Bitmap(~mask).trace(
        turdsize=turdsize, alphamax=1.0, opticurve=True, opttolerance=0.2
    )

    parts: list[str] = []
    for curve in path:
        sx, sy = _xy(curve.start_point)
        parts.append(f"M{sx:.2f} {sy:.2f}")
        for seg in curve.segments:
            ex, ey = _xy(seg.end_point)
            if seg.is_corner:
                cx, cy = _xy(seg.c)
                parts.append(f"L{cx:.2f} {cy:.2f}L{ex:.2f} {ey:.2f}")
            else:
                c1x, c1y = _xy(seg.c1)
                c2x, c2y = _xy(seg.c2)
                parts.append(f"C{c1x:.2f} {c1y:.2f} {c2x:.2f} {c2y:.2f} {ex:.2f} {ey:.2f}")
        parts.append("Z")
    return "".join(parts)


def wrap_edges(img, pad: int):
    """Pad an image with its own opposite edges, the way a tile repeats.

    The left margin is the tile's right edge and vice versa, so a shape running
    off one side continues into the padding exactly as it would in the repeat.
    """
    import numpy as np
    from PIL import Image

    if pad <= 0:
        return img
    arr = np.asarray(img.convert("RGBA"))
    padded = np.pad(arr, ((pad, pad), (pad, pad), (0, 0)), mode="wrap")
    return Image.fromarray(padded, "RGBA")


def wrap_pad_for(size: tuple[int, int]) -> int:
    return max(_MIN_WRAP_PX, int(round(min(size) * _WRAP_SHARE)))


def _document(
    traced: tuple[int, int],
    display: tuple[int, int],
    title: str,
    body: str,
    offset: int = 0,
) -> str:
    """Wrap traced geometry in an SVG.

    `offset` is the seamless wrap: the geometry was traced on a padded canvas,
    so it is shifted back and clipped to the tile, which is what makes the cut
    land exactly on the tile boundary.
    """
    tw, th = traced
    dw, dh = display
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{dw}" height="{dh}" '
        f'viewBox="0 0 {tw} {th}">\n'
        f"  <title>{title}</title>\n"
    )
    if not offset:
        return head + body + "</svg>\n"
    return (
        head
        + "  <defs>\n"
        + '    <clipPath id="tile">\n'
        + f'      <rect x="0" y="0" width="{tw}" height="{th}"/>\n'
        + "    </clipPath>\n"
        + "  </defs>\n"
        + f'  <g clip-path="url(#tile)" transform="translate({-offset} {-offset})">\n'
        + body
        + "  </g>\n"
        + "</svg>\n"
    )


def repeat_preview(tile: Path, dst: Path, times: int = 3) -> Path:
    """Write an SVG that shows the traced tile repeated, for checking the seam.

    A tile looks fine on its own and wrong only when it repeats, so judging one
    by eye in isolation proves nothing. This references the tile rather than
    copying it, so re-tracing updates the preview too.
    """
    from lxml import etree

    tree = etree.parse(str(tile), etree.XMLParser(resolve_entities=False))
    root = tree.getroot()
    box = (root.get("viewBox") or "").split()
    width, height = (float(box[2]), float(box[3])) if len(box) == 4 else (1000.0, 1000.0)

    uses = "".join(
        f'  <image href="{tile.name}" x="{col * width:g}" y="{row * height:g}" '
        f'width="{width:g}" height="{height:g}"/>\n'
        for row in range(times)
        for col in range(times)
    )
    dst.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width * times:g}" height="{height * times:g}" '
        f'viewBox="0 0 {width * times:g} {height * times:g}">\n'
        f"  <title>{tile.stem} repeated {times} by {times}</title>\n"
        f"{uses}</svg>\n",
        encoding="utf-8",
    )
    return dst


def _prepare(src: Path, max_edge: int):
    """Open an image for tracing: alpha kept separately, size capped."""
    from PIL import Image

    from .images import open_image

    with open_image(src) as opened:
        img = opened.convert("RGBA")
        original = img.size
        if max(img.size) > max_edge:
            img = img.copy()
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        return img, original


def _trace_mono(
    src: Path,
    dst: Path,
    detail: str,
    threshold: int,
    invert: bool,
    seamless: bool = False,
) -> str:
    np, _ = _require()
    _, turdsize, max_edge = DETAIL.get(detail, DETAIL["medium"])
    img, original = _prepare(src, max_edge)

    tile_size = img.size
    pad = wrap_pad_for(tile_size) if seamless else 0
    if pad:
        img = wrap_edges(img, pad)

    alpha = np.array(img.getchannel("A"))
    grey = np.array(img.convert("L"))
    # Transparent pixels must not read as black once alpha is discarded.
    grey = np.where(alpha < 128, 255, grey)

    mask = grey < threshold
    if invert:
        mask = ~mask & (alpha >= 128)

    d = _trace_mask(mask, turdsize)
    body = f'  <path d="{d}" fill="#000000" fill-rule="evenodd"/>\n'
    dst.write_text(
        _document(tile_size, original, src.stem, body, offset=pad),
        encoding="utf-8",
    )
    seam = ", seamless" if seamless else ""
    return f"Potrace, threshold {threshold}, speckle {turdsize}{seam}"


def rgba_to_paths(rgba, colors: int = 8, turdsize: int = 4) -> list[str]:
    """Trace an RGBA array into `<path>` elements, one per posterised colour.

    Shared by the tracing tool and by part splitting, which wraps the result in
    a named group per part.
    """
    from PIL import Image

    img = Image.fromarray(rgba) if not isinstance(rgba, Image.Image) else rgba
    return [layer.path for layer in colour_layers(img.convert("RGBA"), colors, turdsize)]


class Layer:
    """One posterised colour: its fill and the path that carries it."""

    __slots__ = ("colour", "d", "pixels")

    def __init__(self, colour: str, d: str, pixels: int) -> None:
        self.colour = colour
        self.d = d
        self.pixels = pixels

    @property
    def path(self) -> str:
        return f'<path d="{self.d}" fill="{self.colour}" fill-rule="evenodd"/>'

    def group(self, index: int) -> str:
        """A named group carrying the fill, so recolouring is one attribute.

        The fill lives on the group rather than the path precisely so that
        changing one colour of a pattern is a single edit in any editor, not a
        select-all-matching-fill hunt.
        """
        return (
            f'  <g id="colour-{index}" data-fill="{self.colour}" fill="{self.colour}">\n'
            f'    <path d="{self.d}" fill-rule="evenodd"/>\n'
            f"  </g>\n"
        )


def colour_layers(img, colors: int, turdsize: int) -> list[Layer]:
    """Posterise to `colors` and trace each colour, largest area first."""
    np, _ = _require()
    from PIL import Image

    colors = max(MIN_COLORS, min(MAX_COLORS, int(colors)))
    opaque = np.array(img.getchannel("A")) >= 128
    quantized = img.convert("RGB").quantize(
        colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
    )
    indices = np.array(quantized)
    palette = quantized.getpalette() or []

    # Largest areas first, so later layers stack on top the way they should.
    counts = [(int((indices == i).sum()), i) for i in np.unique(indices)]
    counts.sort(reverse=True)
    minimum = max(1, int(indices.size * _MIN_LAYER_SHARE))

    layers: list[Layer] = []
    for count, index in counts:
        if count < minimum:
            continue
        mask = (indices == index) & opaque
        if not mask.any():
            continue
        d = _trace_mask(mask, turdsize)
        if not d:
            continue
        r, g, b = palette[index * 3 : index * 3 + 3]
        layers.append(Layer(f"#{r:02x}{g:02x}{b:02x}", d, count))
    return layers


# Kept for callers that only want the raw elements.
def _colour_layers(img, colors: int, turdsize: int) -> list[str]:
    return [layer.path for layer in colour_layers(img, colors, turdsize)]


def _trace_color(
    src: Path,
    dst: Path,
    detail: str,
    colors: int | None = None,
    seamless: bool = False,
) -> str:
    preset_colors, turdsize, max_edge = DETAIL.get(detail, DETAIL["medium"])
    img, original = _prepare(src, max_edge)

    tile_size = img.size
    pad = wrap_pad_for(tile_size) if seamless else 0
    if pad:
        img = wrap_edges(img, pad)

    layers = colour_layers(img, colors or preset_colors, turdsize)
    if not layers:
        raise RuntimeError("Nothing to trace - the image looks empty")

    body = "".join(layer.group(n) for n, layer in enumerate(layers, start=1))
    dst.write_text(
        _document(tile_size, original, src.stem, body, offset=pad),
        encoding="utf-8",
    )
    seam = ", seamless" if seamless else ""
    return f"Potrace, {len(layers)} colour layers, speckle {turdsize}{seam}"


def trace_image(
    src: Path,
    out_dir: Path,
    engine: str = "color",
    detail: str = "medium",
    threshold: int = 128,
    invert: bool = False,
    colors: int | None = None,
    seamless: bool = False,
    preview: bool = False,
    log=None,
) -> TaskResult:
    """Auto-trace one raster image into a standalone .svg file."""
    src = Path(src)
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.svg")

    if engine == "mono":
        note = _trace_mono(src, dst, detail, threshold, invert, seamless=seamless)
    else:
        note = _trace_color(src, dst, detail, colors=colors, seamless=seamless)

    extras: list[Path] = []
    if preview:
        extras.append(repeat_preview(dst, unique_path(dst.with_name(f"{dst.stem} repeat.svg"))))

    if log:
        log(f"  {src.name} -> {dst.name} ({note})")
    return TaskResult(
        source=src,
        output=dst,
        message=note,
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
        extra_outputs=extras,
    )
