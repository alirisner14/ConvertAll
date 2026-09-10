"""Audio -> video wrapping, plus audio/video re-encoding, all via FFmpeg."""

from __future__ import annotations

from pathlib import Path

from .common import TaskResult, ensure_dir, run_ffmpeg, size_of, unique_path

# preset -> (x264 CRF, AAC bitrate)
VIDEO_PRESETS = {
    "lossless": (18, "256k"),
    "balanced": (21, "192k"),
    "small": (26, "128k"),
}
RESOLUTIONS = {
    "1920 x 1080 (1080p)": (1920, 1080),
    "1280 x 720 (720p)": (1280, 720),
    "3840 x 2160 (4K)": (3840, 2160),
    "1080 x 1080 (square)": (1080, 1080),
}


def audio_to_video(
    src: Path,
    out_dir: Path,
    background: Path | None = None,
    resolution: tuple[int, int] = (1920, 1080),
    preset: str = "balanced",
    background_color: str = "black",
    log=None,
) -> TaskResult:
    """Wrap a .wav (or any audio file) into a playable .mp4 container.

    With a background image the still is encoded with `-tune stillimage`, which
    costs almost nothing per frame. Without one we synthesise a flat colour
    track at 5 fps - accepted by every player, near-zero bytes.
    """
    src = Path(src)
    w, h = resolution
    crf, abr = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["balanced"])
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.mp4")

    args: list[str] = []
    if background and Path(background).exists():
        # Scale to fit, then pad to the exact canvas so dimensions stay even.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={background_color},"
            "format=yuv420p"
        )
        args += ["-loop", "1", "-framerate", "5", "-i", str(background)]
        note = f"still image, {w}x{h}"
    else:
        vf = "format=yuv420p"
        args += ["-f", "lavfi", "-i", f"color=c={background_color}:s={w}x{h}:r=5"]
        note = f"blank {background_color} track, {w}x{h}"

    args += [
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-tune",
        "stillimage",
        "-crf",
        str(crf),
        "-g",
        "150",
        "-c:a",
        "aac",
        "-b:a",
        abr,
        "-shortest",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    run_ffmpeg(args, log=log)

    if log:
        log(f"  {src.name} -> {dst.name} ({note}, AAC {abr})")
    return TaskResult(
        source=src,
        output=dst,
        message=f"{note}, AAC {abr}",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


def compress_video(src: Path, out_dir: Path, preset: str = "balanced", log=None) -> TaskResult:
    """Re-encode a video with x264 + AAC at visually-lossless settings."""
    src = Path(src)
    crf, abr = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["balanced"])
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.mp4")
    run_ffmpeg(
        [
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            abr,
            "-movflags",
            "+faststart",
            str(dst),
        ],
        log=log,
    )
    return TaskResult(
        source=src,
        output=dst,
        message=f"x264 crf{crf} / AAC {abr}",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


def compress_audio_lossless(src: Path, out_dir: Path, log=None) -> TaskResult:
    """WAV/AIFF -> FLAC. Bit-for-bit identical audio, typically ~50% smaller."""
    src = Path(src)
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.flac")
    run_ffmpeg(["-i", str(src), "-c:a", "flac", "-compression_level", "8", str(dst)], log=log)
    return TaskResult(
        source=src,
        output=dst,
        message="FLAC (mathematically lossless)",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )
