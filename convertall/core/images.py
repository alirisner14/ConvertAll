"""Image conversion: PNG->WebP, HEIC->PNG/JPG, PNG/JPG->ICO, and friends.

Encoder settings are tuned so the default preset is *visually* lossless: you
should not be able to tell the output from the input at 100% zoom, while still
getting a large file-size reduction.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from .common import TaskResult, ensure_dir, size_of, unique_path

# HEIC/HEIF support is optional; the app degrades gracefully without it.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - depends on environment
    HEIF_OK = False

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# preset -> (webp quality, jpeg quality, png compress level)
PRESETS = {
    "lossless": (95, 95, 9),
    "balanced": (82, 85, 9),
    "small": (68, 74, 9),
}
PRESET_LABELS = {
    "lossless": "Visually lossless",
    "balanced": "Balanced",
    "small": "Smallest file",
}


def open_image(src: Path) -> Image.Image:
    """Open an image, honouring EXIF rotation so nothing lands sideways."""
    if src.suffix.lower() in {".heic", ".heif"} and not HEIF_OK:
        raise RuntimeError("HEIC support missing - run: pip install pillow-heif")
    img = Image.open(src)
    img.load()
    return ImageOps.exif_transpose(img) or img


def _flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """Drop alpha onto a solid background (JPEG has no alpha channel)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, background)
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return img.convert("RGB")


def _is_flat_art(img: Image.Image, limit: int = 256) -> bool:
    """True for logos/line art, where true-lossless WebP beats lossy WebP."""
    try:
        colors = img.convert("RGBA").getcolors(maxcolors=limit * 8)
    except Exception:
        return False
    return colors is not None and len(colors) <= limit


def _square_pad(img: Image.Image, size: int) -> Image.Image:
    """Fit into a transparent square without distorting the aspect ratio."""
    img = img.convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas


def convert_image(
    src: Path,
    out_dir: Path,
    target: str = "webp",
    preset: str = "lossless",
    ico_sizes: tuple[int, ...] = ICO_SIZES,
    max_dimension: int | None = None,
    log=None,
) -> TaskResult:
    """Convert one image file. `target` is webp | png | jpg | ico."""
    src = Path(src)
    target = target.lower().lstrip(".")
    if target == "jpeg":
        target = "jpg"
    webp_q, jpeg_q, png_level = PRESETS.get(preset, PRESETS["lossless"])

    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.{target}")

    with open_image(src) as img:
        if max_dimension and max(img.size) > max_dimension:
            img = img.copy()
            img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        icc = img.info.get("icc_profile")
        note = ""

        if target == "ico":
            sizes = [s for s in sorted(set(ico_sizes)) if s <= 256]
            _square_pad(img, max(sizes)).save(dst, format="ICO", sizes=[(s, s) for s in sizes])
            note = "sizes " + ", ".join(str(s) for s in sizes)

        elif target == "webp":
            use_lossless = preset == "lossless" and _is_flat_art(img)
            src_img = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA")
            extra = {"icc_profile": icc} if icc else {}
            if use_lossless:
                src_img.save(dst, format="WEBP", lossless=True, quality=100, method=6, **extra)
                note = "true lossless (flat-colour artwork)"
            else:
                src_img.save(dst, format="WEBP", quality=webp_q, method=6, **extra)
                note = f"q{webp_q}"

        elif target == "png":
            out = img if img.mode in ("RGB", "RGBA", "L", "LA", "P") else img.convert("RGBA")
            out.save(
                dst,
                format="PNG",
                optimize=True,
                compress_level=png_level,
                icc_profile=icc,
            )
            note = "lossless"

        elif target == "jpg":
            _flatten(img).save(
                dst,
                format="JPEG",
                quality=jpeg_q,
                optimize=True,
                progressive=True,
                subsampling=0 if preset == "lossless" else 2,
                icc_profile=icc,
            )
            note = f"q{jpeg_q}"

        else:
            raise ValueError(f"Unsupported target format: {target}")

    if log:
        log(f"  {src.name} -> {dst.name} ({note})")
    return TaskResult(
        source=src,
        output=dst,
        message=note,
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )
