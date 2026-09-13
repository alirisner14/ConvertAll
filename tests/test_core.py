"""Tests for the processing pipelines. No GUI, no display required."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from PIL import Image

from convertall.core.common import collect_files, human, kind_of, unique_path
from convertall.core.compress import minify_svg, smart_compress
from convertall.core.images import convert_image
from convertall.core.svgsplit import split_svg

LAYERED_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="200" height="100" viewBox="0 0 200 100">
  <defs>
    <linearGradient id="grad"><stop offset="0" stop-color="#f00"/></linearGradient>
  </defs>
  <g inkscape:label="Background" id="l1">
    <rect x="0" y="0" width="200" height="100" fill="url(#grad)"/>
  </g>
  <g inkscape:label="Foreground" id="l2" style="display:none">
    <circle cx="60" cy="50" r="30" fill="#0000ff"/>
    <circle cx="140" cy="50" r="30" fill="#00ff00"/>
  </g>
</svg>
"""

WRAPPED_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
  <g transform="translate(10,10)">
    <g id="a"><rect width="10" height="10"/></g>
    <g id="b"><rect x="20" width="10" height="10"/></g>
    <g id="c"><rect x="40" width="10" height="10"/></g>
  </g>
</svg>
"""

FLAT_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50">
  <rect width="20" height="20"/><circle cx="35" cy="35" r="10"/>
</svg>
"""


@pytest.fixture
def photo(tmp_path):
    """A gradient PNG - many colours, so it takes the lossy WebP path."""
    img = Image.new("RGB", (160, 120))
    img.putdata([(x % 256, y % 256, (x * y) % 256) for y in range(120) for x in range(160)])
    path = tmp_path / "photo.png"
    img.save(path)
    return path


@pytest.fixture
def logo(tmp_path):
    """A two-colour PNG with alpha - the flat-artwork path."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(16, 48):
        for y in range(16, 48):
            img.putpixel((x, y), (255, 0, 0, 255))
    path = tmp_path / "logo.png"
    img.save(path)
    return path


# --- helpers ---------------------------------------------------------------- #


def test_kind_of():
    from pathlib import Path

    assert kind_of(Path("a.PNG")) == "image"
    assert kind_of(Path("a.wav")) == "audio"
    assert kind_of(Path("a.mp4")) == "video"
    assert kind_of(Path("a.svg")) == "vector"
    assert kind_of(Path("a.txt")) == "other"


def test_unique_path_never_clobbers(tmp_path):
    first = tmp_path / "x.png"
    first.write_bytes(b"1")
    assert unique_path(first).name == "x (2).png"


def test_collect_files_filters_and_dedupes(tmp_path, photo):
    (tmp_path / "notes.txt").write_text("ignore me")
    found = collect_files([tmp_path, photo], {".png"})
    assert found == [photo]


def test_human_readable_sizes():
    assert human(512) == "512 B"
    assert human(2048).startswith("2.0 KB")


# --- images ----------------------------------------------------------------- #


@pytest.mark.parametrize("target", ["webp", "png", "jpg", "ico"])
def test_convert_image_targets(photo, tmp_path, target):
    out = tmp_path / "out"
    result = convert_image(photo, out, target=target)
    assert result.ok and result.output.exists()
    assert result.output.suffix == f".{target}"
    with Image.open(result.output) as img:
        assert img.size[0] > 0


def test_png_to_webp_shrinks_the_file(photo, tmp_path):
    result = convert_image(photo, tmp_path / "out", target="webp", preset="balanced")
    assert result.bytes_out < result.bytes_in


def test_flat_artwork_uses_true_lossless_webp(logo, tmp_path):
    result = convert_image(logo, tmp_path / "out", target="webp", preset="lossless")
    assert "lossless" in result.message
    with Image.open(result.output) as img:
        assert img.mode in ("RGBA", "RGB")


def test_ico_contains_every_requested_size(logo, tmp_path):
    result = convert_image(logo, tmp_path / "out", target="ico", ico_sizes=(16, 32, 48))
    with Image.open(result.output) as ico:
        assert {size[0] for size in ico.info["sizes"]} == {16, 32, 48}


def test_jpg_output_has_no_alpha(logo, tmp_path):
    result = convert_image(logo, tmp_path / "out", target="jpg")
    with Image.open(result.output) as img:
        assert img.mode == "RGB"


def test_max_dimension_downscales(photo, tmp_path):
    result = convert_image(photo, tmp_path / "out", target="png", max_dimension=64)
    with Image.open(result.output) as img:
        assert max(img.size) == 64


# --- svg splitting ---------------------------------------------------------- #


def test_split_svg_by_layer(tmp_path):
    src = tmp_path / "layered.svg"
    src.write_text(LAYERED_SVG, encoding="utf-8")
    result = split_svg(src, tmp_path / "out")

    files = [result.output, *result.extra_outputs]
    assert len(files) == 2
    names = sorted(f.name for f in files)
    assert "Background" in names[0] and "Foreground" in names[1]

    # defs are carried across, the viewBox is preserved, hidden layers are shown
    foreground = files[1].read_text(encoding="utf-8")
    assert "linearGradient" in foreground
    assert 'viewBox="0 0 200 100"' in foreground
    assert "display:none" not in foreground


def test_split_svg_unwraps_a_single_container_group(tmp_path):
    src = tmp_path / "wrapped.svg"
    src.write_text(WRAPPED_SVG, encoding="utf-8")
    result = split_svg(src, tmp_path / "out")

    files = [result.output, *result.extra_outputs]
    assert len(files) == 3
    # the wrapper's transform must be re-applied so nothing shifts
    assert "translate(10,10)" in files[0].read_text(encoding="utf-8")


def test_split_svg_falls_back_to_shapes(tmp_path):
    src = tmp_path / "flat.svg"
    src.write_text(FLAT_SVG, encoding="utf-8")
    result = split_svg(src, tmp_path / "out")
    assert len([result.output, *result.extra_outputs]) == 2


def test_split_svg_rejects_a_single_layer(tmp_path):
    src = tmp_path / "one.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>', encoding="utf-8")
    with pytest.raises(RuntimeError, match="nothing to split"):
        split_svg(src, tmp_path / "out")


# --- compression ------------------------------------------------------------ #


def test_minify_svg_strips_editor_metadata(tmp_path):
    src = tmp_path / "layered.svg"
    src.write_text(LAYERED_SVG, encoding="utf-8")
    result = minify_svg(src, tmp_path / "out")
    assert "inkscape" not in result.output.read_text(encoding="utf-8")


def test_smart_compress_keeps_the_original_when_it_cannot_win(logo, tmp_path):
    result = smart_compress(logo, tmp_path / "out", preset="lossless")
    assert result.ok
    assert result.bytes_out <= result.bytes_in


def test_smart_compress_leaves_lossy_audio_alone(tmp_path):
    fake_mp3 = tmp_path / "song.mp3"
    fake_mp3.write_bytes(b"\x00" * 1024)
    result = smart_compress(fake_mp3, tmp_path / "out")
    assert result.ok and "already lossy" in result.message


def test_keep_original_uses_the_source_extension(tmp_path):
    """A kept original must not inherit the re-encode's extension."""
    from convertall.core.common import TaskResult
    from convertall.core.compress import _keep_original

    src = tmp_path / "clip.mkv"
    src.write_bytes(b"original bytes")
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "clip.mp4"
    stale.write_bytes(b"bigger re-encode")

    result = _keep_original(
        TaskResult(source=src, output=stale, bytes_in=14, bytes_out=16), src, out, "kept"
    )

    assert not stale.exists(), "the discarded re-encode should be deleted"
    assert result.output.name == "clip.mkv"
    assert result.output.read_bytes() == b"original bytes"
    assert result.bytes_out == 14


def test_smart_compress_reports_unsupported_types(tmp_path):
    odd = tmp_path / "notes.txt"
    odd.write_text("hello")
    result = smart_compress(odd, tmp_path / "out")
    assert not result.ok


# --- tracing ---------------------------------------------------------------- #


def test_mono_engine_emits_valid_svg(logo, tmp_path):
    from lxml import etree

    from convertall.core.vectorize import trace_image

    result = trace_image(logo, tmp_path / "out", engine="mono", threshold=200)
    assert result.ok
    root = etree.parse(str(result.output)).getroot()
    assert etree.QName(root).localname == "svg"
    assert root.findall(".//{http://www.w3.org/2000/svg}path")


def test_mono_engine_traces_the_shape_not_the_background(tmp_path):
    """The classic Potrace footgun: tracing the negative of what you meant."""
    import re

    from convertall.core.vectorize import trace_image

    src = tmp_path / "block.png"
    img = Image.new("RGB", (100, 60), (255, 255, 255))
    for x in range(10, 40):
        for y in range(5, 25):
            img.putpixel((x, y), (0, 0, 0))
    img.save(src)

    result = trace_image(src, tmp_path / "out", engine="mono", detail="high")

    from lxml import etree

    paths = etree.parse(str(result.output)).getroot().findall(".//{http://www.w3.org/2000/svg}path")
    numbers = [float(n) for n in re.findall(r"-?\d+\.\d+", "".join(p.get("d") for p in paths))]
    xs, ys = numbers[0::2], numbers[1::2]

    # The traced outline must hug the black block, not the whole canvas.
    assert min(xs) >= 8 and max(xs) <= 42, f"x span {min(xs)}..{max(xs)}"
    assert min(ys) >= 3 and max(ys) <= 27, f"y span {min(ys)}..{max(ys)}"


def test_color_engine_stacks_one_layer_per_colour(tmp_path):
    from lxml import etree

    from convertall.core.vectorize import trace_image

    src = tmp_path / "bands.png"
    img = Image.new("RGB", (120, 60), (255, 255, 255))
    for x in range(0, 40):
        for y in range(60):
            img.putpixel((x, y), (255, 0, 0))
    for x in range(40, 80):
        for y in range(60):
            img.putpixel((x, y), (0, 0, 255))
    img.save(src)

    result = trace_image(src, tmp_path / "out", engine="color", detail="low")
    assert result.ok
    paths = etree.parse(str(result.output)).getroot().findall(".//{http://www.w3.org/2000/svg}path")
    assert len(paths) >= 3, "expected a layer per colour band"
    assert all(p.get("fill", "").startswith("#") for p in paths)


def test_color_engine_ignores_transparent_regions(logo, tmp_path):
    from lxml import etree

    from convertall.core.vectorize import trace_image

    result = trace_image(logo, tmp_path / "out", engine="color", detail="low")
    paths = etree.parse(str(result.output)).getroot().findall(".//{http://www.w3.org/2000/svg}path")
    # The logo is one red square on transparency - it must not become a
    # full-canvas background layer plus a hole.
    assert 1 <= len(paths) <= 2


# --- audio to video (needs FFmpeg) ------------------------------------------ #


def _ffmpeg_available() -> bool:
    try:
        from convertall.core.common import ffmpeg_exe

        subprocess.run([ffmpeg_exe(), "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_wav_to_mp4_produces_a_playable_container(tmp_path):
    from convertall.core.common import ffmpeg_exe
    from convertall.core.media import audio_to_video

    wav = tmp_path / "tone.wav"
    subprocess.run(
        [ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)],
        capture_output=True,
        check=True,
    )
    result = audio_to_video(wav, tmp_path / "out", resolution=(320, 240), preset="small")
    assert result.ok and result.output.suffix == ".mp4"
    assert result.output.stat().st_size > 0


@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_compressing_an_efficient_video_keeps_the_original(tmp_path):
    """Re-encoding already-tight video makes it bigger. Don't ship that."""
    from convertall.core.common import ffmpeg_exe

    src = tmp_path / "tight.mp4"
    subprocess.run(
        [
            ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=320x240:r=10:d=2",
            "-vf",
            "geq=random(1)*255:128:128",
            "-c:v",
            "libx264",
            "-crf",
            "40",
            "-pix_fmt",
            "yuv420p",
            str(src),
        ],
        capture_output=True,
        check=True,
    )

    # preset="lossless" is CRF 18 - far denser than the CRF 40 source above.
    result = smart_compress(src, tmp_path / "out", preset="lossless")

    assert result.ok
    assert "original kept" in result.message, result.message
    assert result.bytes_out == result.bytes_in
    assert result.output.read_bytes() == src.read_bytes()


@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_compressing_a_wasteful_video_actually_shrinks_it(tmp_path):
    """The guard must not fire on video that genuinely compresses."""
    from convertall.core.common import ffmpeg_exe

    src = tmp_path / "wasteful.mp4"
    subprocess.run(
        [
            ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x480:r=15:d=3",
            "-c:v",
            "libx264",
            "-qp",
            "0",
            "-pix_fmt",
            "yuv420p",
            str(src),
        ],
        capture_output=True,
        check=True,
    )

    result = smart_compress(src, tmp_path / "out", preset="balanced")

    assert result.ok
    assert "original kept" not in result.message
    assert result.bytes_out < result.bytes_in


def test_unknown_video_codec_is_rejected():
    from convertall.core.media import _video_args

    with pytest.raises(ValueError, match="Unknown video codec"):
        _video_args("vp9", "balanced")


def test_codec_crf_tables_cover_every_codec_and_preset():
    from convertall.core.images import PRESET_LABELS
    from convertall.core.media import VIDEO_CODECS, VIDEO_CRF

    assert set(VIDEO_CRF) == set(VIDEO_CODECS)
    for codec, rows in VIDEO_CRF.items():
        assert set(rows) == set(PRESET_LABELS), f"{codec} is missing a preset"


@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
@pytest.mark.parametrize("codec", ["h264", "h265", "av1"])
def test_every_codec_produces_a_playable_file(tmp_path, codec):
    from convertall.core.common import available_encoders, ffmpeg_exe
    from convertall.core.media import _CODEC_ENCODER, compress_video

    encoders = available_encoders()
    if encoders and _CODEC_ENCODER[codec] not in encoders:
        pytest.skip(f"this FFmpeg build has no {_CODEC_ENCODER[codec]}")

    src = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=10:d=1",
            "-c:v",
            "libx264",
            "-qp",
            "0",
            "-pix_fmt",
            "yuv420p",
            str(src),
        ],
        capture_output=True,
        check=True,
    )

    result = compress_video(src, tmp_path / "out", preset="small", codec=codec)
    assert result.ok and result.output.exists()
    assert result.bytes_out > 0
    assert _CODEC_ENCODER[codec] in result.message

    # FFmpeg must be able to decode what we just wrote.
    probe = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(result.output), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_wav_compresses_to_flac(tmp_path):
    from convertall.core.common import ffmpeg_exe
    from convertall.core.media import compress_audio_lossless

    wav = tmp_path / "tone.wav"
    subprocess.run(
        [ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)],
        capture_output=True,
        check=True,
    )
    result = compress_audio_lossless(wav, tmp_path / "out")
    assert result.ok and result.bytes_out < result.bytes_in
