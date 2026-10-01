"""Tests for the Conversion tool's format matrix and dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from convertall.core.convert import (
    IMAGE_TARGETS,
    TARGET_HINTS,
    TARGET_LABELS,
    convert_file,
    targets_for,
    targets_for_file,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("photo.png", set(IMAGE_TARGETS)),
        ("photo.JPG", set(IMAGE_TARGETS)),
        ("shot.heic", set(IMAGE_TARGETS)),
        ("lecture.wav", {"mp3", "mp4", "flac"}),
        ("lecture.aiff", {"mp3", "mp4", "flac"}),
        ("song.mp3", {"mp4"}),  # no MP3 -> MP3: loss for nothing
        ("song.flac", {"mp3", "mp4"}),
        ("clip.mp4", {"mp4"}),
        ("clip.mov", {"mp4"}),
        ("art.svg", set()),
        ("notes.txt", set()),
    ],
)
def test_targets_for_file(name, expected):
    assert set(targets_for_file(Path(name))) == expected


def test_flac_is_only_offered_for_lossless_sources():
    """Re-encoding an MP3 to FLAC makes it bigger and no better."""
    assert "flac" in targets_for_file(Path("a.wav"))
    assert "flac" not in targets_for_file(Path("a.mp3"))
    assert "flac" not in targets_for_file(Path("a.flac"))


def test_targets_for_is_the_intersection():
    assert targets_for([Path("a.png"), Path("b.jpg")]) == list(IMAGE_TARGETS)
    # An image and an audio file share nothing.
    assert targets_for([Path("a.png"), Path("b.wav")]) == []
    # Two audio files, only one of them lossless.
    assert targets_for([Path("a.wav"), Path("b.mp3")]) == ["mp4"]
    assert targets_for([Path("a.wav"), Path("b.flac")]) == ["mp3", "mp4"]


def test_targets_for_is_empty_without_files():
    assert targets_for([]) == []


def test_every_target_has_a_label_and_a_hint():
    for kind in ("png", "wav", "mp4"):
        for target in targets_for_file(Path(f"x.{kind}")):
            assert target in TARGET_LABELS
            assert TARGET_HINTS.get(target)


def test_convert_file_rejects_an_impossible_target(tmp_path):
    src = tmp_path / "photo.png"
    Image.new("RGB", (8, 8)).save(src)
    with pytest.raises(RuntimeError, match="cannot be converted"):
        convert_file(src, tmp_path / "out", target="flac")


@pytest.mark.parametrize("target", ["webp", "png", "jpg", "ico"])
def test_convert_file_routes_images(tmp_path, target):
    src = tmp_path / "photo.png"
    Image.new("RGB", (32, 24), (10, 120, 200)).save(src)

    result = convert_file(src, tmp_path / "out", target=target)

    assert result.ok
    assert result.output.suffix == f".{target}"
    with Image.open(result.output) as img:
        assert img.size[0] > 0


def test_convert_file_honours_max_dimension(tmp_path):
    src = tmp_path / "photo.png"
    Image.new("RGB", (200, 100)).save(src)

    result = convert_file(src, tmp_path / "out", target="png", max_dimension=50)

    with Image.open(result.output) as img:
        assert max(img.size) == 50


# --- HEIC ------------------------------------------------------------------- #
# iPhone photos arrive as HEIC and almost nothing outside Apple opens them, so
# PNG/JPG out of HEIC is a headline case rather than an edge one.

heif = pytest.importorskip("pillow_heif", reason="pillow-heif is not installed")


@pytest.fixture
def heic(tmp_path):
    heif.register_heif_opener()
    img = Image.new("RGB", (120, 80))
    img.putdata([(x * 2 % 256, y * 3 % 256, 90) for y in range(80) for x in range(120)])
    path = tmp_path / "IMG_0042.heic"
    img.save(path, format="HEIF")
    return path


def test_heic_offers_png_and_jpg(heic):
    offered = targets_for_file(heic)
    assert "png" in offered and "jpg" in offered


@pytest.mark.parametrize("target", ["png", "jpg", "webp"])
def test_heic_converts(tmp_path, heic, target):
    result = convert_file(heic, tmp_path / "out", target=target)
    assert result.ok
    assert result.output.suffix == f".{target}"
    with Image.open(result.output) as out:
        assert out.size == (120, 80)


def test_heic_honours_max_dimension(tmp_path, heic):
    result = convert_file(heic, tmp_path / "out", target="png", max_dimension=60)
    with Image.open(result.output) as out:
        assert max(out.size) == 60


# --- MP3 -------------------------------------------------------------------- #


def _tone(path: Path, seconds: float = 1.0) -> Path:
    """A real WAV, written by hand so the test needs no fixture files."""
    import math
    import struct
    import wave

    rate = 44100
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        frames = int(rate * seconds)
        out.writeframes(
            b"".join(
                struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(frames)
            )
        )
    return path


def test_wav_converts_to_mp3(tmp_path):
    src = _tone(tmp_path / "lecture.wav")
    result = convert_file(src, tmp_path / "out", target="mp3")
    assert result.ok
    assert result.output.suffix == ".mp3"
    assert result.output.stat().st_size > 0


def test_mp3_is_much_smaller_than_the_wav(tmp_path):
    src = _tone(tmp_path / "lecture.wav", seconds=2.0)
    result = convert_file(src, tmp_path / "out", target="mp3")
    assert result.bytes_out < result.bytes_in / 2


def test_a_smaller_mp3_preset_produces_a_smaller_file(tmp_path):
    src = _tone(tmp_path / "lecture.wav", seconds=2.0)
    best = convert_file(src, tmp_path / "best", target="mp3", preset="lossless")
    small = convert_file(src, tmp_path / "small", target="mp3", preset="small")
    assert small.bytes_out < best.bytes_out


def test_the_mp3_is_actually_decodable(tmp_path):
    """A file with an .mp3 name proves nothing; FFmpeg has to be able to read it."""
    from convertall.core.common import probe_duration

    src = _tone(tmp_path / "lecture.wav", seconds=2.0)
    result = convert_file(src, tmp_path / "out", target="mp3")
    duration = probe_duration(str(result.output))
    assert duration is not None
    assert 1.8 < duration < 2.3
