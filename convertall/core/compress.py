"""Smart compression: pick the right optimisation for whatever you drop in.

The rule the whole module follows: never trade away quality you would notice.

* Raster images  - re-encoded in place with optimal encoder settings; flat
  artwork goes true-lossless. If the result is not smaller, the original is
  kept instead.
* WAV / AIFF     - FLAC. Bit-for-bit identical audio, usually about half the size.
* Already-lossy audio (MP3/AAC/OGG) - left alone. Re-encoding lossy audio only
  destroys it.
* Video          - x264 CRF + AAC, faststart for instant playback. Kept only
  if the re-encode is actually smaller; already-efficient or newer-codec video
  can grow under H.264, and that is never handed back as a success.
* SVG            - editor cruft stripped and coordinates rounded, geometry untouched.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from lxml import etree

from .common import (
    LOSSY_AUDIO_EXTS,
    TaskResult,
    ensure_dir,
    kind_of,
    size_of,
    unique_path,
)
from .images import convert_image
from .media import compress_audio_lossless, compress_video

EDITOR_NS = (
    "http://www.inkscape.org/namespaces/inkscape",
    "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd",
    "http://ns.adobe.com/AdobeIllustrator/10.0/",
    "http://www.serif.com/",
)
_LONG_FLOAT = re.compile(r"-?\d+\.\d{3,}")


def _round_floats(text: str, places: int = 2) -> str:
    return _LONG_FLOAT.sub(lambda m: f"{float(m.group()):.{places}f}".rstrip("0").rstrip("."), text)


def minify_svg(src: Path, out_dir: Path, log=None) -> TaskResult:
    """Strip editor metadata and over-long coordinates. Geometry is preserved."""
    src = Path(src)
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.svg")

    parser = etree.XMLParser(remove_comments=True, resolve_entities=False, huge_tree=True)
    tree = etree.parse(str(src), parser)
    root = tree.getroot()

    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        qname = etree.QName(el)
        if qname.namespace in EDITOR_NS or qname.localname == "metadata":
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
            continue
        for attr in list(el.attrib):
            if attr.startswith("{") and attr.split("}")[0][1:] in EDITOR_NS:
                del el.attrib[attr]
            elif attr in ("d", "points", "transform"):
                el.set(attr, _round_floats(el.get(attr)))

    etree.cleanup_namespaces(root)
    tree.write(str(dst), xml_declaration=True, encoding="utf-8")

    if size_of(dst) >= size_of(src):
        shutil.copy2(src, dst)
        note = "already minimal - original kept"
    else:
        note = "metadata stripped, coordinates rounded"

    if log:
        log(f"  {src.name} -> {dst.name} ({note})")
    return TaskResult(
        source=src,
        output=dst,
        message=note,
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


def _grew(result: TaskResult) -> bool:
    """True when a re-encode did not actually pay for itself."""
    return bool(result.ok and result.output and result.bytes_out >= result.bytes_in > 0)


def _keep_original(result: TaskResult, src: Path, out_dir: Path, why: str, log=None) -> TaskResult:
    """Throw away a re-encode that got bigger and keep the source bytes.

    The copy is written under the *source* name, not the re-encode's. The two
    can differ - a GIF is re-encoded to PNG, an MKV to MP4 - and copying the
    original bytes into the new extension would produce a mislabelled file.
    """
    if result.output and result.output.exists():
        result.output.unlink()

    dst = unique_path(Path(out_dir) / src.name)
    shutil.copy2(src, dst)

    result.output = dst
    result.message = why
    result.bytes_out = size_of(dst)
    if log:
        log(f"  {src.name} -> {dst.name} ({why})")
    return result


def smart_compress(
    src: Path,
    out_dir: Path,
    preset: str = "lossless",
    images_to_webp: bool = False,
    log=None,
) -> TaskResult:
    """Compress any supported file with settings appropriate to its type."""
    src = Path(src)
    kind = kind_of(src)
    ext = src.suffix.lower()

    if kind == "image":
        target = "webp" if images_to_webp else {".jpeg": "jpg"}.get(ext, ext.lstrip("."))
        if target in ("gif", "bmp", "tif", "tiff", "heic", "heif", "avif"):
            target = "png"  # formats Pillow cannot re-encode well; PNG is safe
        result = convert_image(src, out_dir, target=target, preset=preset, log=log)
        # Asking for WebP is a deliberate format change, so honour it even if it
        # does not shrink. Everything else is meant to be an optimisation.
        if not images_to_webp and _grew(result):
            return _keep_original(result, src, out_dir, "already optimal - original kept", log)
        return result

    if kind == "audio":
        if ext in LOSSY_AUDIO_EXTS:
            ensure_dir(out_dir)
            dst = unique_path(Path(out_dir) / src.name)
            shutil.copy2(src, dst)
            return TaskResult(
                source=src,
                output=dst,
                message="already lossy - copied untouched (re-encoding would degrade it)",
                bytes_in=size_of(src),
                bytes_out=size_of(dst),
            )
        return compress_audio_lossless(src, out_dir, log=log)

    if kind == "video":
        result = compress_video(src, out_dir, preset=preset, log=log)
        # Video is the likeliest place for a re-encode to backfire: anything
        # already efficiently encoded, or in a newer codec than H.264, can come
        # out larger *and* slightly worse. Never hand that back as a success.
        if _grew(result):
            return _keep_original(
                result, src, out_dir, "already efficiently encoded - original kept", log
            )
        return result

    if kind == "vector":
        return minify_svg(src, out_dir, log=log)

    return TaskResult(source=src, ok=False, message=f"unsupported file type ({ext})")
