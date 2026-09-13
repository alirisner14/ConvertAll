"""Which formats a file can become, and how to get it there.

The Conversion tool asks two questions: *what can this file turn into?* and
*please turn it into that.* This module answers both, so the GUI never has to
know which pipeline handles which format.
"""

from __future__ import annotations

from pathlib import Path

from .common import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, TaskResult, kind_of
from .images import convert_image
from .media import audio_to_mp4, compress_audio_lossless, compress_video

# Formats the Conversion tool can produce, in the order they should be offered.
IMAGE_TARGETS = ("webp", "png", "jpg", "ico")
AUDIO_TARGETS = ("mp4",)
VIDEO_TARGETS = ("mp4",)

# FLAC is only worth offering for audio that is still lossless. Re-encoding an
# MP3 to FLAC makes a bigger file that sounds no better.
LOSSLESS_AUDIO_EXTS = {".wav", ".aiff", ".aif"}

TARGET_LABELS = {
    "webp": "WebP",
    "png": "PNG",
    "jpg": "JPG",
    "ico": "ICO",
    "mp4": "MP4",
    "flac": "FLAC",
}

TARGET_HINTS = {
    "webp": "Smallest for the web. Keeps transparency.",
    "png": "Lossless, keeps transparency. Large but exact.",
    "jpg": "Photographs. No transparency.",
    "ico": "Windows icon, every size packed into one file.",
    "mp4": "Video container - plays anywhere that accepts video.",
    "flac": "Lossless audio, typically about half the size.",
}

ACCEPTED = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS


def targets_for_file(path: Path) -> tuple[str, ...]:
    """Formats a single file can be converted into."""
    path = Path(path)
    kind = kind_of(path)
    if kind == "image":
        return IMAGE_TARGETS
    if kind == "audio":
        if path.suffix.lower() in LOSSLESS_AUDIO_EXTS:
            return (*AUDIO_TARGETS, "flac")
        return AUDIO_TARGETS
    if kind == "video":
        return VIDEO_TARGETS
    return ()


def targets_for(paths) -> list[str]:
    """Formats every one of these files can become.

    The intersection, deliberately. Offering a target that only some of the
    batch can reach means a run that silently does less than it looks like it
    will - better to say plainly that the selection has nothing in common.
    """
    paths = list(paths)
    if not paths:
        return []

    shared: set[str] | None = None
    for path in paths:
        available = set(targets_for_file(path))
        shared = available if shared is None else shared & available

    order = [*IMAGE_TARGETS, "mp4", "flac"]
    return [target for target in order if target in (shared or set())]


def convert_file(
    src: Path,
    out_dir: Path,
    target: str,
    preset: str = "lossless",
    max_dimension: int | None = None,
    background: Path | None = None,
    resolution: tuple[int, int] = (1920, 1080),
    background_color: str = "black",
    video_codec: str = "h264",
    log=None,
) -> TaskResult:
    """Convert one file into `target`, routing to whichever pipeline fits."""
    src = Path(src)
    target = target.lower().lstrip(".")
    if target == "jpeg":
        target = "jpg"

    if target not in targets_for_file(src):
        raise RuntimeError(f"{src.suffix or 'This file'} cannot be converted to {target.upper()}")

    if target in IMAGE_TARGETS:
        return convert_image(
            src, out_dir, target=target, preset=preset, max_dimension=max_dimension, log=log
        )

    if target == "flac":
        return compress_audio_lossless(src, out_dir, log=log)

    if target == "mp4":
        if kind_of(src) == "audio":
            return audio_to_mp4(
                src,
                out_dir,
                background=background,
                resolution=resolution,
                preset=preset,
                background_color=background_color,
                log=log,
            )
        return compress_video(src, out_dir, preset=preset, codec=video_codec, log=log)

    raise RuntimeError(f"Unsupported target format: {target}")
