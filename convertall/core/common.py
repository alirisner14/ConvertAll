"""Shared helpers: file classification, FFmpeg discovery, task results."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".heic",
    ".heif",
    ".avif",
}
AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
VECTOR_EXTS = {".svg"}
LOSSY_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".opus"}

# Hide the console window FFmpeg would otherwise flash on Windows.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class TaskResult:
    """Outcome of converting a single input file."""

    source: Path
    output: Path | None = None
    ok: bool = True
    message: str = ""
    bytes_in: int = 0
    bytes_out: int = 0
    extra_outputs: list[Path] = field(default_factory=list)

    @property
    def saved_pct(self) -> float:
        if not self.bytes_in or not self.bytes_out:
            return 0.0
        return (1.0 - self.bytes_out / self.bytes_in) * 100.0

    def summary(self) -> str:
        if not self.ok:
            return f"FAILED  {self.source.name} - {self.message}"
        bits = [self.source.name]
        if self.output:
            bits.append(f"-> {self.output.name}")
        if self.extra_outputs:
            bits.append(f"(+{len(self.extra_outputs)} more)")
        if self.bytes_in and self.bytes_out:
            bits.append(
                f"[{human(self.bytes_in)} -> {human(self.bytes_out)}, {self.saved_pct:+.0f}%]"
            )
        if self.message:
            bits.append(f"- {self.message}")
        return "  ".join(bits)


def human(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024.0 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in VECTOR_EXTS:
        return "vector"
    return "other"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_path(path: Path) -> Path:
    """Never clobber an existing file: foo.png -> foo (2).png."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def size_of(path: Path | None) -> int:
    try:
        return path.stat().st_size if path else 0
    except OSError:
        return 0


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """System FFmpeg if present, otherwise the wheel bundled by imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "FFmpeg was not found. Install it and put it on PATH, or run:\n"
            "    pip install imageio-ffmpeg"
        ) from exc


def run_ffmpeg(args: list[str], log=None) -> None:
    """Run FFmpeg with the given arguments, raising on a non-zero exit."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    if log:
        log(" ".join(f'"{a}"' if " " in a else a for a in cmd[1:]))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(" | ".join(tail[-3:]) or f"FFmpeg exited {proc.returncode}")


def collect_files(paths, exts: set[str] | None = None, recursive: bool = True) -> list[Path]:
    """Expand a mixed list of files and folders into a sorted file list."""
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            out.extend(f for f in it if f.is_file())
        elif p.is_file():
            out.append(p)
    if exts:
        out = [f for f in out if f.suffix.lower() in exts]
    seen, unique = set(), []
    for f in out:
        key = str(f.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return sorted(unique)


def default_output_dir(sources: list[Path], name: str = "ConvertAll Output") -> Path:
    """Sensible default: a sibling folder next to the first input."""
    if sources:
        return Path(sources[0]).parent / name
    return Path.home() / "Documents" / name
