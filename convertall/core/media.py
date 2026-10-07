"""Audio -> MP4 conversion, plus audio/video re-encoding, all via FFmpeg."""

from __future__ import annotations

from pathlib import Path

from .common import (
    TaskResult,
    available_encoders,
    ensure_dir,
    probe_dimensions,
    probe_duration,
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
    progress=None,
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
    run_ffmpeg(args, log=log, on_progress=progress, duration=probe_duration(str(src)))

    if log:
        log(f"  {src.name} -> {dst.name} ({note}, AAC {abr})")
    return TaskResult(
        source=src,
        output=dst,
        message=f"{note}, AAC {abr}",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


# Heights offered for rescaling. Width follows the source's aspect ratio.
RESOLUTIONS_OUT = {
    0: "Keep original",
    2160: "2160p (4K)",
    1440: "1440p",
    1080: "1080p",
    720: "720p",
    480: "480p",
    360: "360p",
}
MIN_HEIGHT, MAX_HEIGHT = 144, 4320


def scale_filter(height: int, upscale: bool) -> str:
    """An FFmpeg scale filter for a target height, preserving aspect ratio.

    -2 keeps the aspect ratio and rounds the width to an even number, which
    yuv420p requires. Without `upscale` the height is capped at the source's
    own, expressed in-filter so no probe is needed and a mixed batch does the
    right thing per file rather than per batch.
    """
    target = f"min(ih,{height})" if not upscale else str(height)
    return f"scale=-2:'{target}':flags=lanczos"


# Rescaling guidance. These are rules of thumb, not physics, but they are the
# ones that hold up: enlarging invents no detail, and shrinking too far costs
# legibility long before it costs "quality" in any abstract sense.
#
# Upscaling: beyond twice the original height the softness is obvious on any
# screen big enough to notice, because every added pixel is interpolated.
# Downscaling: below a third of the original height, small text and fine lines
# stop being readable - which matters most for the recordings and screencasts
# people most often want to shrink.
UPSCALE_LIMIT = 2.0
DOWNSCALE_LIMIT = 1 / 3
# ...and a floor that does not scale with the source, because legibility is
# absolute: 360p is hard to read whether it came from 720p or from 4K.
DOWNSCALE_FLOOR = 432


def _nearest_rung(height: float, at_or_below: bool) -> int:
    """Snap a limit to a height the menu actually offers."""
    rungs = sorted(h for h in RESOLUTIONS_OUT if h)
    if at_or_below:
        candidates = [h for h in rungs if h <= height]
        return candidates[-1] if candidates else rungs[0]
    candidates = [h for h in rungs if h >= height]
    return candidates[0] if candidates else rungs[-1]


def rescale_advice(source_height: int, target_height: int = 0, upscale: bool = False) -> str:
    """What is realistic for this source, and whether the current pick exceeds it.

    Returns "" when there is nothing useful to say, so the note only appears
    where it earns its space.
    """
    if not source_height:
        return ""

    highest = _nearest_rung(source_height * UPSCALE_LIMIT, at_or_below=True)
    lowest = _nearest_rung(max(DOWNSCALE_FLOOR, source_height * DOWNSCALE_LIMIT), at_or_below=False)

    if target_height and target_height > source_height and upscale:
        if target_height > highest:
            return (
                f"Note: it is not recommended to upscale above {highest}p for videos "
                f"with a starting resolution of {source_height}p. Enlarging adds "
                "pixels, never detail."
            )
        return (
            f"{source_height}p to {target_height}p will look softer than the "
            "original. Nothing is gained in detail, and the file gets bigger."
        )

    if target_height and target_height < source_height and target_height < lowest:
        return (
            f"Note: it is not recommended to downscale below {lowest}p for videos "
            f"with a starting resolution of {source_height}p. Small text and fine "
            "lines stop being readable first."
        )

    return (
        f"Source is {source_height}p. For this video, {lowest}p is about as low as "
        f"is sensible, and upscaling past {highest}p is not recommended."
    )


def compress_video(
    src: Path,
    out_dir: Path,
    preset: str = "balanced",
    codec: str = "h264",
    height: int = 0,
    upscale: bool = False,
    log=None,
    progress=None,
) -> TaskResult:
    """Re-encode a video at visually-lossless settings in the chosen codec."""
    src = Path(src)
    _, abr = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["balanced"])
    video_args, label = _video_args(codec, preset)

    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.mp4")
    scaling: list[str] = []
    if height:
        height = max(MIN_HEIGHT, min(MAX_HEIGHT, int(height)))
        scaling = ["-vf", scale_filter(height, upscale)]
        size = probe_dimensions(str(src))
        if size:
            label += f" / {size[1]}p -> {height if upscale else min(size[1], height)}p"
        else:
            label += f" / {height}p"

    base = [
        "-i",
        str(src),
        *scaling,
        *video_args,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]

    # Copying the audio stream is both faster and better than re-encoding it:
    # the source is usually already lossy, and a second pass through AAC only
    # loses quality. Fall back when the stream cannot live in MP4 (e.g. PCM).
    duration = probe_duration(str(src))
    try:
        run_ffmpeg(
            [*base, "-c:a", "copy", str(dst)], log=log, on_progress=progress, duration=duration
        )
        audio = "audio copied"
    except RuntimeError:
        dst.unlink(missing_ok=True)
        run_ffmpeg(
            [*base, "-c:a", "aac", "-b:a", abr, str(dst)],
            log=log,
            on_progress=progress,
            duration=duration,
        )
        audio = f"AAC {abr}"

    return TaskResult(
        source=src,
        output=dst,
        message=f"{label} / {audio}",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


def compress_audio_lossless(src: Path, out_dir: Path, log=None, progress=None) -> TaskResult:
    """WAV/AIFF -> FLAC. Bit-for-bit identical audio, typically ~50% smaller."""
    src = Path(src)
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.flac")
    run_ffmpeg(
        ["-i", str(src), "-c:a", "flac", "-compression_level", "8", str(dst)],
        log=log,
        on_progress=progress,
        duration=probe_duration(str(src)),
    )
    return TaskResult(
        source=src,
        output=dst,
        message="FLAC (mathematically lossless)",
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )


# preset -> (LAME VBR quality, what to tell the user). -q:a 0 is LAME's best
# VBR setting, around 245 kbps; 2 is the long-standing "transparent for most
# listeners" default; 5 is for when size matters more than fidelity.
MP3_QUALITY = {
    "lossless": (0, "V0 VBR, about 245 kbps"),
    "balanced": (2, "V2 VBR, about 190 kbps"),
    "small": (5, "V5 VBR, about 130 kbps"),
}


# What to call the presets when the output is MP3. The image wording ("visually
# lossless") would be a lie here: every MP3 setting discards audio.
MP3_PRESET_LABELS = {
    "lossless": "Highest quality (~245 kbps)",
    "balanced": "Balanced (~190 kbps)",
    "small": "Smallest file (~130 kbps)",
}


def convert_audio_mp3(
    src: Path,
    out_dir: Path,
    preset: str = "lossless",
    log=None,
    progress=None,
) -> TaskResult:
    """Any audio -> MP3 via LAME.

    MP3 is a lossy format, so this always discards some audio - there is no
    setting that does not. The highest preset is chosen to be inaudible rather
    than labelled lossless, because calling it lossless would be untrue.
    """
    src = Path(src)
    if "libmp3lame" not in available_encoders():
        raise RuntimeError("This FFmpeg build has no MP3 encoder (libmp3lame).")

    quality, note = MP3_QUALITY.get(preset, MP3_QUALITY["lossless"])
    ensure_dir(out_dir)
    dst = unique_path(Path(out_dir) / f"{src.stem}.mp3")
    run_ffmpeg(
        [
            "-i",
            str(src),
            "-vn",  # cover art would otherwise be re-encoded as a video stream
            "-c:a",
            "libmp3lame",
            "-q:a",
            str(quality),
            "-map_metadata",
            "0",
            "-id3v2_version",
            "3",
            str(dst),
        ],
        log=log,
        on_progress=progress,
        duration=probe_duration(str(src)),
    )
    return TaskResult(
        source=src,
        output=dst,
        message=note,
        bytes_in=size_of(src),
        bytes_out=size_of(dst),
    )
