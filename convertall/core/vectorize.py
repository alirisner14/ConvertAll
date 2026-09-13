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

# Colour layers smaller than this share of the image are dropped as noise.
_MIN_LAYER_SHARE = 0.0008


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


def _document(traced: tuple[int, int], display: tuple[int, int], title: str, body: str) -> str:
    tw, th = traced
    dw, dh = display
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{dw}" height="{dh}" '
        f'viewBox="0 0 {tw} {th}">\n'
        f"  <title>{title}</title>\n"
        f"{body}"
        f"</svg>\n"
    )


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


def _trace_mono(src: Path, dst: Path, detail: str, threshold: int, invert: bool) -> str:
    np, _ = _require()
    _, turdsize, max_edge = DETAIL.get(detail, DETAIL["medium"])
    img, original = _prepare(src, max_edge)

    alpha = np.array(img.getchannel("A"))
    grey = np.array(img.convert("L"))
    # Transparent pixels must not read as black once alpha is discarded.
    grey = np.where(alpha < 128, 255, grey)

    mask = grey < threshold
    if invert:
        mask = ~mask & (alpha >= 128)

    d = _trace_mask(mask, turdsize)
    body = f'  <path d="{d}" fill="#000000" fill-rule="evenodd"/>\n'
    dst.write_text(_document(img.size, original, src.stem, body), encoding="utf-8")
    return f"Potrace, threshold {threshold}, speckle {turdsize}"


def rgba_to_paths(rgba, colors: int = 8, turdsize: int = 4) -> list[str]:
    """Trace an RGBA array into `<path>` elements, one per posterised colour.

    Shared by the tracing tool and by part splitting, which wraps the result in
    a named group per part.
    """
    from PIL import Image

    img = Image.fromarray(rgba) if not isinstance(rgba, Image.Image) else rgba
    return _colour_layers(img.convert("RGBA"), colors, turdsize)


def _colour_layers(img, colors: int, turdsize: int) -> list[str]:
    np, _ = _require()
    from PIL import Image

    opaque = np.array(img.getchannel("A")) >= 128
    quantized = img.convert("RGB").quantize(
        colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
    )
    indices = np.array(quantized)
    palette = quantized.getpalette() or []

    counts = [(int((indices == i).sum()), i) for i in np.unique(indices)]
    counts.sort(reverse=True)
    minimum = max(1, int(indices.size * _MIN_LAYER_SHARE))

    layers: list[str] = []
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
        layers.append(f'<path d="{d}" fill="#{r:02x}{g:02x}{b:02x}" fill-rule="evenodd"/>')
    return layers


def _trace_color(src: Path, dst: Path, detail: str) -> str:
    np, _ = _require()
    from PIL import Image

    colors, turdsize, max_edge = DETAIL.get(detail, DETAIL["medium"])
    img, original = _prepare(src, max_edge)

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

    layers: list[str] = []
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
        layers.append(f'  <path d="{d}" fill="#{r:02x}{g:02x}{b:02x}" fill-rule="evenodd"/>\n')

    if not layers:
        raise RuntimeError("Nothing to trace - the image looks empty")

    dst.write_text(_document(img.size, original, src.stem, "".join(layers)), encoding="utf-8")
    return f"Potrace, {len(layers)} colour layers, speckle {turdsize}"


def trace_image(
    src: Path,
    out_dir: Path,
    engine: str = "color",
    detail: str = "medium",
    threshold: int = 128,
    invert: bool = False,
    log=None,
) -> TaskResult:
    """Auto-trace one raster image into a standalone .svg file."""
    src = Path(src)
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.svg")

    if engine == "mono":
        note = _trace_mono(src, dst, detail, threshold, invert)
    else:
        note = _trace_color(src, dst, detail)

    if log:
        log(f"  {src.name} -> {dst.name} ({note})")
    return TaskResult(
        source=src,
        output=dst,
        message=note,
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )
