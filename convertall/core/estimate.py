"""Rough "how big will this end up" guesses for the file list.

These are ratios observed on ordinary material, not predictions. A file's real
output depends on its content - noise compresses badly, flat colour compresses
brilliantly - so everything here is presented to the user as an estimate and
never used to make a decision. The one thing it must not do is mislead: where
no sensible guess exists, it returns None and the column stays blank.
"""

from __future__ import annotations

from pathlib import Path

from .common import kind_of, size_of

# target -> output/input ratio for a typical raster image
IMAGE_RATIOS = {
    "webp": {"lossless": 0.38, "balanced": 0.22, "small": 0.14},
    "jpg": {"lossless": 0.55, "balanced": 0.30, "small": 0.18},
    "png": {"lossless": 0.92, "balanced": 0.92, "small": 0.88},
    "ico": {"lossless": 0.45, "balanced": 0.45, "small": 0.45},
}

# codec -> ratio against an H.264 source at the same visual quality
VIDEO_RATIOS = {
    "h264": {"lossless": 0.95, "balanced": 0.70, "small": 0.45},
    "h265": {"lossless": 0.78, "balanced": 0.55, "small": 0.34},
    "av1": {"lossless": 0.62, "balanced": 0.42, "small": 0.26},
}

LOSSLESS_AUDIO = {".wav", ".aiff", ".aif"}

# MP3 out of uncompressed PCM. CD-quality WAV is a fixed 1411 kbps, so the
# ratio is simply the target bitrate over that - no probing needed. Sources at
# other sample rates land somewhat off, which is what "~" is for.
MP3_FROM_PCM = {"lossless": 0.17, "balanced": 0.135, "small": 0.092}


def _downscale_factor(src: Path, max_dimension: int | None) -> float:
    """How much smaller the pixel count gets, or 1.0 if nothing is resized.

    Reading the header is enough for the size, so this does not decode the
    image. File size tracks area, not edge length, hence the square.
    """
    if not max_dimension:
        return 1.0
    try:
        from PIL import Image

        with Image.open(src) as img:
            longest = max(img.size)
    except Exception:  # pragma: no cover - unreadable or unsupported header
        return 1.0
    if longest <= max_dimension:
        return 1.0
    return (max_dimension / longest) ** 2


def _height_factor(src: Path, height: int, upscale: bool) -> float:
    """How rescaling changes the size: bitrate tracks pixel count, so area.

    Upscaling is deliberately treated as free rather than expensive - adding
    pixels adds no detail, and the encoder spends little on them - so the guess
    stays at 1.0 instead of claiming a file will balloon.
    """
    if not height:
        return 1.0
    from .common import probe_dimensions

    size = probe_dimensions(str(src))
    if not size or not size[1]:
        return 1.0
    if height >= size[1]:
        return 1.0
    return (height / size[1]) ** 2


def estimate_output_bytes(
    src: Path,
    target: str | None = None,
    preset: str = "lossless",
    video_codec: str = "h264",
    max_dimension: int | None = None,
    height: int = 0,
    upscale: bool = False,
) -> int | None:
    """Rough output size in bytes, or None when there is no honest guess."""
    src = Path(src)
    original = size_of(src)
    if not original:
        return None

    kind = kind_of(src)
    ext = src.suffix.lower().lstrip(".")
    target = (target or "").lower().lstrip(".") or None
    if target == "jpeg":
        target = "jpg"

    if kind == "image":
        chosen = target if target in IMAGE_RATIOS else ext if ext in IMAGE_RATIOS else "webp"
        shrink = _downscale_factor(src, max_dimension)
        # Re-encoding a format into itself rarely moves much.
        ratio = 0.9 if chosen == ext and chosen != "webp" else IMAGE_RATIOS[chosen].get(preset, 0.3)
        return int(original * ratio * shrink)

    if kind == "video":
        ratio = VIDEO_RATIOS.get(video_codec, VIDEO_RATIOS["h264"]).get(preset, 0.6)
        return int(original * ratio * _height_factor(src, height, upscale))

    if kind == "audio":
        if target == "mp4":
            return None  # depends entirely on the video track chosen alongside it
        if target == "mp3":
            if f".{ext}" in LOSSLESS_AUDIO:
                return int(original * MP3_FROM_PCM.get(preset, MP3_FROM_PCM["lossless"]))
            # Re-encoding something already compressed: the input's own bitrate
            # decides the answer and we have not measured it, so say nothing.
            return None
        if f".{ext}" in LOSSLESS_AUDIO:
            return int(original * 0.55)  # FLAC on ordinary PCM
        return original  # already lossy: copied untouched

    if kind == "vector":
        return int(original * 0.85)

    return None


def estimate_label(src: Path, **kwargs) -> str:
    """Human-readable estimate for the file list, or an em dash when unknown."""
    from .common import human

    guess = estimate_output_bytes(src, **kwargs)
    return f"~{human(guess)}" if guess else "—"
