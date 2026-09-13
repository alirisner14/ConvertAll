"""Split a sprite into labelled, animation-ready parts.

Three ways to say where the parts are, because different artwork wants
different approaches - measured on real sprites, not guessed:

* **mask** - the painted mask *is* the answer. Fully manual, fully predictable.
  The only thing that always works, including where the art has no contour to
  find (a head that flows into a body with nothing drawn between them).
* **grow** - paint a rough stroke per part and let it grow to the artwork's own
  contours. Near one-click on outlined art; needs touching up on soft or furry
  art, where texture creates false edges.
* **cut** - draw lines through the sprite and take whatever regions fall out.
  Good when parts are obvious but painting each one is tedious.

Whichever is used, every part then gets its cut edge replicated outward so it
tucks under its neighbour and no gap opens when the part rotates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .common import TaskResult, ensure_dir, size_of, unique_path

METHODS = {
    "grow": "Painted strokes, grown to the artwork's edges",
    "mask": "Painted mask, used exactly as painted",
    "cut": "Cut lines, split into whatever regions result",
}

# A mask colour covering fewer pixels than this is a stray brush dab, not a part.
MIN_PART_SHARE = 0.0005
ALPHA_FLOOR = 128


@dataclass
class Part:
    """One extracted piece, on the full original canvas so it stays in register."""

    label: str
    rgba: np.ndarray
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    pixels: int
    extended_pixels: int = 0

    def manifest_entry(self) -> dict:
        x0, y0, x1, y1 = self.bbox
        return {
            "label": self.label,
            "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "centroid": {"x": self.centroid[0], "y": self.centroid[1]},
            "pixels": self.pixels,
            "extended_pixels": self.extended_pixels,
        }


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Splitting into parts needs OpenCV - run: pip install opencv-python"
        ) from exc
    return cv2


def _load_rgba(path: Path) -> np.ndarray:
    from .images import open_image

    with open_image(Path(path)) as opened:
        return np.array(opened.convert("RGBA"), dtype=np.uint8)


def _mask_regions(
    mask_rgba: np.ndarray, total_pixels: int
) -> dict[tuple[int, int, int], np.ndarray]:
    """Every distinct opaque colour in the mask becomes a candidate part."""
    opaque = mask_rgba[:, :, 3] > ALPHA_FLOOR
    if not opaque.any():
        raise RuntimeError("The parts mask is fully transparent - nothing was painted")

    flat = mask_rgba[:, :, :3].reshape(-1, 3)
    keys = (flat[:, 0].astype(np.int32) << 16) | (flat[:, 1].astype(np.int32) << 8) | flat[:, 2]
    keys = keys.reshape(mask_rgba.shape[:2])

    minimum = max(1, int(total_pixels * MIN_PART_SHARE))
    regions: dict[tuple[int, int, int], np.ndarray] = {}
    for key in np.unique(keys[opaque]):
        region = (keys == key) & opaque
        if region.sum() < minimum:
            continue
        colour = (int(key >> 16) & 255, int(key >> 8) & 255, int(key) & 255)
        regions[colour] = region
    if not regions:
        raise RuntimeError("No painted region in the mask is large enough to be a part")
    return regions


def _partition_mask(alpha: np.ndarray, regions: dict) -> dict[tuple, np.ndarray]:
    """Trust the painting. Clipped to the sprite so stray strokes do nothing."""
    body = alpha > ALPHA_FLOOR
    return {colour: (region & body) for colour, region in regions.items()}


def _partition_grow(rgb: np.ndarray, alpha: np.ndarray, regions: dict) -> dict[tuple, np.ndarray]:
    """Grow each painted stroke to the artwork's own contours.

    Watershed, not GrabCut. GrabCut models colour, so it cannot separate a tail
    from a body of the same colour however clearly the art draws the boundary
    between them - measured, it took 85-99% of the sprite every time.
    """
    cv2 = _require_cv2()
    smooth = cv2.pyrMeanShiftFiltering(np.ascontiguousarray(rgb), sp=12, sr=24)

    markers = np.zeros(alpha.shape, np.int32)
    markers[alpha <= ALPHA_FLOOR] = 1
    order = list(regions)
    for index, colour in enumerate(order, start=2):
        markers[regions[colour]] = index

    cv2.watershed(cv2.cvtColor(smooth, cv2.COLOR_RGB2BGR), markers)

    body = alpha > ALPHA_FLOOR
    return {colour: ((markers == index + 2) & body) for index, colour in enumerate(order)}


def _partition_cut(
    alpha: np.ndarray, cut: np.ndarray, total_pixels: int
) -> dict[tuple, np.ndarray]:
    """Remove the drawn lines, then take whatever islands remain."""
    cv2 = _require_cv2()
    body = (alpha > ALPHA_FLOOR) & ~cut
    count, labels, stats, _ = cv2.connectedComponentsWithStats(body.astype(np.uint8), 8)
    minimum = max(1, int(total_pixels * MIN_PART_SHARE))

    found = {}
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] < minimum:
            continue
        # Synthesise a stable colour key so every method returns the same shape.
        found[(index, index, index)] = labels == index
    if not found:
        raise RuntimeError("The cut lines did not leave any region large enough to be a part")
    return found


def _extend(
    rgb: np.ndarray, alpha: np.ndarray, piece: np.ndarray, amount: int
) -> tuple[np.ndarray, int, np.ndarray]:
    """Replicate the cut-edge pixels outward so the part tucks under its neighbour.

    Only into territory that is still artwork. The silhouette edge borders
    transparency and must never grow, or the whole outline fattens.
    """
    cv2 = _require_cv2()
    piece_u8 = piece.astype(np.uint8) * 255
    if amount <= 0 or not piece.any():
        return piece.copy(), 0, rgb.copy()

    grown = cv2.dilate(piece_u8, np.ones((3, 3), np.uint8), iterations=amount)
    allowed = (grown > 0) & (alpha > ALPHA_FLOOR)
    new = allowed & ~piece
    if not new.any():
        return piece.copy(), 0, rgb.copy()

    # Nearest piece pixel for each new pixel - that *is* "replicate the edge rows",
    # and it follows the cut at any angle rather than assuming a flat edge.
    _, index = cv2.distanceTransformWithLabels(
        (~piece).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    ys, xs = np.nonzero(piece)
    own = index[piece]
    lut_y = np.zeros(int(own.max()) + 1, np.int32)
    lut_x = np.zeros(int(own.max()) + 1, np.int32)
    lut_y[own], lut_x[own] = ys, xs

    safe = np.clip(index, 0, len(lut_y) - 1)
    filled = piece | new
    out_rgb = np.zeros_like(rgb)
    out_rgb[piece] = rgb[piece]
    out_rgb[new] = rgb[lut_y[safe][new], lut_x[safe][new]]
    return filled, int(new.sum()), out_rgb


def split_into_parts(
    src: Path,
    mask: Path,
    method: str = "grow",
    extend_px: int = 40,
    names: dict[str, str] | None = None,
    log=None,
) -> list[Part]:
    """Split `src` using `mask`, returning one `Part` per region."""
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method}. Choose from {', '.join(METHODS)}")

    sprite = _load_rgba(Path(src))
    painted = _load_rgba(Path(mask))
    if painted.shape[:2] != sprite.shape[:2]:
        raise RuntimeError(
            f"The mask is {painted.shape[1]}x{painted.shape[0]} but the sprite is "
            f"{sprite.shape[1]}x{sprite.shape[0]} - they must match"
        )

    rgb, alpha = sprite[:, :, :3], sprite[:, :, 3]
    total = max(int((alpha > ALPHA_FLOOR).sum()), 1)

    if method == "cut":
        regions = _partition_cut(alpha, painted[:, :, 3] > ALPHA_FLOOR, total)
    else:
        painted_regions = _mask_regions(painted, total)
        regions = (
            _partition_grow(rgb, alpha, painted_regions)
            if method == "grow"
            else _partition_mask(alpha, painted_regions)
        )

    names = names or {}
    parts: list[Part] = []
    ordered = sorted(regions.items(), key=lambda kv: -kv[1].sum())
    for index, (colour, piece) in enumerate(ordered, 1):
        if not piece.any():
            continue
        filled, added, filled_rgb = _extend(rgb, alpha, piece, extend_px)

        rgba = np.zeros((*piece.shape, 4), np.uint8)
        rgba[filled, :3] = filled_rgb[filled]
        rgba[filled, 3] = 255

        ys, xs = np.nonzero(filled)
        key = "#{:02x}{:02x}{:02x}".format(*colour)
        label = names.get(key) or names.get(str(index)) or f"part-{index:02d}"
        parts.append(
            Part(
                label=label,
                rgba=rgba,
                bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                centroid=(int(xs.mean()), int(ys.mean())),
                pixels=int(piece.sum()),
                extended_pixels=added,
            )
        )
        if log:
            log(f"  {label}: {piece.sum() / total * 100:.0f}% of the sprite, +{added}px overlap")

    if not parts:
        raise RuntimeError("Nothing was extracted - check the mask covers the sprite")
    return parts


def export_parts(
    src: Path,
    parts: list[Part],
    out_dir: Path,
    fmt: str = "png",
    log=None,
) -> TaskResult:
    """Write every part, plus a manifest describing where each one belongs."""
    from PIL import Image

    src = Path(src)
    target = ensure_dir(Path(out_dir) / src.stem)
    written: list[Path] = []

    if fmt == "png":
        # Full canvas, so the parts drop back on top of each other in register
        # with no offset arithmetic anywhere downstream.
        for part in parts:
            dst = unique_path(target / f"{src.stem}_{part.label}.png")
            Image.fromarray(part.rgba).save(dst)
            written.append(dst)
    elif fmt == "svg":
        written.append(_export_svg(src, parts, target))
    else:
        raise ValueError(f"Unsupported format: {fmt}. Choose png or svg")

    manifest = target / f"{src.stem}_parts.json"
    manifest.write_text(
        json.dumps(
            {
                "source": src.name,
                "canvas": {
                    "width": int(parts[0].rgba.shape[1]),
                    "height": int(parts[0].rgba.shape[0]),
                },
                "parts": [p.manifest_entry() for p in parts],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    written.append(manifest)

    if log:
        log(f"  {len(parts)} parts -> {target.name}\\")
    return TaskResult(
        source=src,
        output=written[0],
        message=f"{len(parts)} parts ({fmt.upper()}) + manifest",
        bytes_in=size_of(src),
        bytes_out=sum(size_of(p) for p in written),
        extra_outputs=written[1:],
    )


def _export_svg(src: Path, parts: list[Part], target: Path) -> Path:
    """One SVG, each part its own named group so a rig can address it."""
    from .vectorize import rgba_to_paths

    height, width = parts[0].rgba.shape[:2]
    body = [
        f'  <g id="{part.label}" inkscape:label="{part.label}">\n'
        + "".join(f"    {p}\n" for p in rgba_to_paths(part.rgba))
        + "  </g>\n"
        for part in parts
    ]
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"  <title>{src.stem}</title>\n" + "".join(body) + "</svg>\n"
    )
    dst = unique_path(target / f"{src.stem}_parts.svg")
    dst.write_text(svg, encoding="utf-8")
    return dst
