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
        ("lecture.wav", {"mp4", "flac"}),
        ("lecture.aiff", {"mp4", "flac"}),
        ("song.mp3", {"mp4"}),
        ("song.flac", {"mp4"}),
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
