"""Tests for the file-list size estimates and the elapsed/remaining clock.

The estimates are guesses by design. What matters is that they never mislead:
a guess is only offered where one is defensible, and the direction is right.
"""

from __future__ import annotations

import pytest
from PIL import Image

from convertall.app import _clock
from convertall.core.estimate import estimate_label, estimate_output_bytes


@pytest.fixture
def photo(tmp_path):
    img = Image.new("RGB", (300, 200))
    img.putdata([(x % 256, y % 256, (x * y) % 256) for y in range(200) for x in range(300)])
    path = tmp_path / "photo.png"
    img.save(path)
    return path


def test_a_missing_file_has_no_estimate(tmp_path):
    assert estimate_output_bytes(tmp_path / "nope.png") is None


def test_unknown_types_have_no_estimate(tmp_path):
    odd = tmp_path / "notes.txt"
    odd.write_text("hello")
    assert estimate_output_bytes(odd) is None
    assert estimate_label(odd) == "—"


def test_webp_is_estimated_smaller_than_the_png(photo):
    original = photo.stat().st_size
    guess = estimate_output_bytes(photo, target="webp")
    assert guess is not None
    assert 0 < guess < original


def test_a_smaller_preset_estimates_a_smaller_file(photo):
    lossless = estimate_output_bytes(photo, target="webp", preset="lossless")
    small = estimate_output_bytes(photo, target="webp", preset="small")
    assert small < lossless


def test_better_codecs_estimate_smaller_video(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00" * 5_000_000)

    h264 = estimate_output_bytes(clip, video_codec="h264", preset="balanced")
    h265 = estimate_output_bytes(clip, video_codec="h265", preset="balanced")
    av1 = estimate_output_bytes(clip, video_codec="av1", preset="balanced")

    assert av1 < h265 < h264, "the ranking must match what the codecs actually do"


def test_lossy_audio_is_estimated_unchanged(tmp_path):
    """Compression copies it untouched, so the estimate must say so."""
    song = tmp_path / "song.mp3"
    song.write_bytes(b"\x00" * 4096)
    assert estimate_output_bytes(song) == 4096


def test_wav_is_estimated_smaller_for_flac(tmp_path):
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"\x00" * 10_000)
    guess = estimate_output_bytes(wav)
    assert 0 < guess < 10_000


def test_audio_to_mp4_declines_to_guess(tmp_path):
    """The output size depends on the video track, so no honest number exists."""
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"\x00" * 10_000)
    assert estimate_output_bytes(wav, target="mp4") is None


def test_the_label_marks_estimates_as_approximate(photo):
    label = estimate_label(photo, target="webp")
    assert label.startswith("~"), "an estimate must not look like a measurement"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "—"),
        (0, "0:00"),
        (5, "0:05"),
        (65, "1:05"),
        (600, "10:00"),
        (3600, "1:00:00"),
        (7325, "2:02:05"),
        (-4, "0:00"),
    ],
)
def test_clock_formatting(seconds, expected):
    assert _clock(seconds) == expected
