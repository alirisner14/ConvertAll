"""Split a layered .svg into one standalone .svg per layer / group / shape.

Universal by design - it does not assume Illustrator, Inkscape or Figma output:

1. Top-level ``<g>`` elements are treated as layers.
2. A single wrapper ``<g>`` (very common) is transparently unwrapped, and any
   transform it carried is re-applied to each extracted layer so nothing moves.
3. If the file has no groups at all, every top-level drawable shape becomes its
   own file.

``<defs>`` and ``<style>`` blocks are copied into every output, so gradients,
filters, clip paths and CSS classes keep working in the split files. The
original ``viewBox`` is preserved, which means the pieces stay in register and
can be layered straight back on top of each other.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from lxml import etree

from .common import TaskResult, ensure_dir, size_of, unique_path

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

DRAWABLE = {
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "image",
    "use",
    "g",
    "switch",
    "foreignObject",
}
SHARED = {"defs", "style", "symbol", "clipPath", "mask", "marker", "filter"}

MODES = {
    "auto": "Auto (layers, then shapes)",
    "groups": "Groups / layers only",
    "shapes": "Every individual shape",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _tag(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _safe_name(text: str, fallback: str) -> str:
    cleaned = _UNSAFE.sub("-", (text or "").strip()).strip("-")
    return cleaned[:60] or fallback


def _label_of(el, index: int) -> str:
    for key in (f"{{{INKSCAPE_NS}}}label", "data-name", "id", "class"):
        value = el.get(key)
        if value:
            return _safe_name(value, f"layer-{index:02d}")
    return f"{_tag(el) or 'item'}-{index:02d}"


def _pick_layers(root, mode: str) -> tuple[list, str]:
    """Return the elements to split out, plus a transform to re-apply."""
    if mode == "shapes":
        leaves = [
            el
            for el in root.iter()
            if _tag(el) in DRAWABLE - {"g", "switch"} and el.getparent() is not None
        ]
        return leaves, ""

    node, carried = root, []
    while True:
        groups = [c for c in node if _tag(c) == "g"]
        others = [c for c in node if _tag(c) in DRAWABLE and _tag(c) != "g"]
        # Unwrap a lone container group that only exists to hold the real layers.
        if len(groups) == 1 and not others:
            inner = groups[0]
            inner_groups = [c for c in inner if _tag(c) == "g"]
            if len(inner_groups) >= 2:
                if inner.get("transform"):
                    carried.append(inner.get("transform"))
                node = inner
                continue
        break

    groups = [c for c in node if _tag(c) == "g"]
    transform = " ".join(carried)
    if groups and mode in ("auto", "groups"):
        return groups, transform
    if mode == "groups":
        return [], transform
    return [c for c in node if _tag(c) in DRAWABLE], transform


def _shell(root):
    """An empty copy of the root <svg>, keeping its attributes and namespaces."""
    shell = copy.deepcopy(root)
    for child in list(shell):
        shell.remove(child)
    return shell


def split_svg(
    src: Path,
    out_dir: Path,
    mode: str = "auto",
    subfolder_per_file: bool = True,
    log=None,
) -> TaskResult:
    """Split one .svg file. Returns the first output plus every extra file."""
    src = Path(src)
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, huge_tree=True)
    tree = etree.parse(str(src), parser)
    root = tree.getroot()

    if _tag(root) != "svg":
        raise RuntimeError("Not an SVG file (root element is not <svg>)")

    layers, carried = _pick_layers(root, mode)
    if not layers:
        raise RuntimeError("Nothing to split - no groups or shapes found")
    if len(layers) == 1:
        raise RuntimeError("Only one layer found - nothing to split apart")

    shared = [copy.deepcopy(el) for el in root if _tag(el) in SHARED]

    target = Path(out_dir) / _safe_name(src.stem, "svg") if subfolder_per_file else Path(out_dir)
    ensure_dir(target)

    written: list[Path] = []
    for index, layer in enumerate(layers, start=1):
        shell = _shell(root)
        for el in shared:
            shell.append(copy.deepcopy(el))

        piece = copy.deepcopy(layer)
        # A hidden Inkscape layer should still render once it stands alone.
        style = piece.get("style", "")
        if "display:none" in style.replace(" ", ""):
            piece.set("style", re.sub(r"display\s*:\s*none;?", "", style))

        if carried:
            wrapper = etree.SubElement(shell, f"{{{SVG_NS}}}g")
            wrapper.set("transform", carried)
            wrapper.append(piece)
        else:
            shell.append(piece)

        name = _label_of(layer, index)
        dst = unique_path(target / f"{index:02d}_{name}.svg")
        etree.ElementTree(shell).write(
            str(dst), xml_declaration=True, encoding="utf-8", pretty_print=True
        )
        written.append(dst)

    if log:
        log(f"  {src.name} -> {len(written)} files in {target.name}\\")
    return TaskResult(
        source=src,
        output=written[0],
        message=f"{len(written)} layers ({MODES.get(mode, mode)})",
        bytes_in=size_of(src),
        bytes_out=sum(size_of(p) for p in written),
        extra_outputs=written[1:],
    )
