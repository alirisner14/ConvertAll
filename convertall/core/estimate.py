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


def estimate_output_bytes(
    src: Path,
    target: str | None = None,
    preset: str = "lossless",
    video_codec: str = "h264",
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
        # Re-encoding a format into itself rarely moves much.
        if chosen == ext and chosen != "webp":
            return int(original * 0.9)
        return int(original * IMAGE_RATIOS[chosen].get(preset, 0.3))

    if kind == "video":
        return int(original * VIDEO_RATIOS.get(video_codec, VIDEO_RATIOS["h264"]).get(preset, 0.6))

    if kind == "audio":
        if target == "mp4":
            return None  # depends entirely on the video track chosen alongside it
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
