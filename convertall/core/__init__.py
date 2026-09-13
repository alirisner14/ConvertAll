"""Processing pipelines. Every function here is GUI-free and unit-testable."""

from .common import (
    AUDIO_EXTS,
    IMAGE_EXTS,
    VECTOR_EXTS,
    VIDEO_EXTS,
    TaskResult,
    collect_files,
    default_output_dir,
    ffmpeg_exe,
    human,
    kind_of,
)
from .compress import minify_svg, smart_compress
from .images import convert_image
from .media import audio_to_mp4, compress_audio_lossless, compress_video
from .svgsplit import split_svg
from .vectorize import trace_image

__all__ = [
    "AUDIO_EXTS",
    "IMAGE_EXTS",
    "VECTOR_EXTS",
    "VIDEO_EXTS",
    "TaskResult",
    "audio_to_mp4",
    "collect_files",
    "compress_audio_lossless",
    "compress_video",
    "convert_image",
    "default_output_dir",
    "ffmpeg_exe",
    "human",
    "kind_of",
    "minify_svg",
    "smart_compress",
    "split_svg",
    "trace_image",
]
