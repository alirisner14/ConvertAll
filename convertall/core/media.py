"""Audio -> MP4 conversion, plus audio/video re-encoding, all via FFmpeg."""

from __future__ import annotations

from pathlib import Path

from .common import (
    TaskResult,
    available_encoders,
    ensure_dir,
    run_ffmpeg,
    size_of,
    unique_path,
)

# preset -> (x264 CRF, AAC bitrate)
VIDEO_PRESETS = {
    "lossless": (18, "256k"),
    "balanced": (21, "192k"),
    "small": (26, "128k"),
}

# Codecs offered for re-compression, cheapest CPU first. Measured on
# screen-recording content against an x264 source: H.265 saves about 17%,
# AV1 about 34% - roughly double, for roughly four times the encode time.
VIDEO_CODECS = {
    "h264": "H.264 - fastest, plays on anything",
    "h265": "H.265 / HEVC - smaller, ~2x slower",
    "av1": "AV1 - smallest, much slower",
}
_CODEC_ENCODER = {"h264": "libx264", "h265": "libx265", "av1": "libaom-av1"}

# CRF is not comparable across codecs; these rows are tuned to look equivalent.
VIDEO_CRF = {
    "h264": {"lossless": 18, "balanced": 21, "small": 26},
    "h265": {"lossless": 22, "balanced": 26, "small": 30},
    "av1": {"lossless": 28, "balanced": 35, "small": 42},
}


def _video_args(codec: str, preset: str) -> tuple[list[str], str]:
    """FFmpeg video arguments for a codec/preset pair, plus a label."""
    encoder = _CODEC_ENCODER.get(codec)
    if encoder is None:
        raise ValueError(f"Unknown video codec: {codec}")

    installed = available_encoders()
    if installed and encoder not in installed:
        raise RuntimeError(
            f"This FFmpeg build has no {encoder}, so {VIDEO_CODECS[codec]} is "
            "unavailable. Install a full FFmpeg build, or choose H.264."
        )

    crf = VIDEO_CRF[codec].get(preset, VIDEO_CRF[codec]["balanced"])
    if codec == "h265":
        # hvc1 rather than hev1, or QuickTime and iOS refuse to play it.
        args = ["-c:v", "libx265", "-preset", "medium", "-crf", str(crf), "-tag:v", "hvc1"]
    elif codec == "av1":
        # libaom is the slow reference encoder; cpu-used 8 with row threading
        # keeps it usable on long recordings without giving up much size.
        args = [
            "-c:v",
            "libaom-av1",
            "-crf",
            str(crf),
            "-b:v",
            "0",
            "-cpu-used",
            "8",
            "-row-mt",
            "1",
        ]
    else:
        args = ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf)]
    return args, f"{encoder} crf{crf}"


RESOLUTIONS = {
    "1920 x 1080 (1080p)": (1920, 1080),
    "1280 x 720 (720p)": (1280, 720),
    "3840 x 2160 (4K)": (3840, 2160),
    "1080 x 1080 (square)": (1080, 1080),
}


def audio_to_mp4(
    src: Path,
    out_dir: Path,
    background: Path | None = None,
    resolution: tuple[int, int] = (1920, 1080),
    preset: str = "balanced",
    background_color: str = "black",
    log=None,
) -> TaskResult:
    """Convert a .wav (or any audio file) into a playable .mp4.

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


def compress_video(
    src: Path,
    out_dir: Path,
    preset: str = "balanced",
    codec: str = "h264",
    log=None,
) -> TaskResult:
    """Re-encode a video at visually-lossless settings in the chosen codec."""
    src = Path(src)
    _, abr = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["balanced"])
    video_args, label = _video_args(codec, preset)

    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.mp4")
    base = ["-i", str(src), *video_args, "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

    # Copying the audio stream is both faster and better than re-encoding it:
    # the source is usually already lossy, and a second pass through AAC only
    # loses quality. Fall back when the stream cannot live in MP4 (e.g. PCM).
    try:
        run_ffmpeg([*base, "-c:a", "copy", str(dst)], log=log)
        audio = "audio copied"
    except RuntimeError:
        dst.unlink(missing_ok=True)
        run_ffmpeg([*base, "-c:a", "aac", "-b:a", abr, str(dst)], log=log)
        audio = f"AAC {abr}"

    return TaskResult(
        source=src,
        output=dst,
        message=f"{label} / {audio}",
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
