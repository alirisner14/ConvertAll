"""Naming the output something other than the input's name.

The field is optional, so the first rule is that an empty or unusable entry
changes nothing. The second is that one name across a batch must not collide:
numbering is what makes the feature safe to use on more than one file.
"""

from __future__ import annotations

import contextlib
import time

import pytest
from PIL import Image

from convertall.core.common import clean_stem, numbered_stem, rename_output
from convertall.core.convert import convert_file
from convertall.jobs import JobRunner


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("holiday photo", "holiday photo"),
        ("  padded  ", "padded"),
        ("", ""),
        ("   ", ""),
        ("...", ""),
        ("///", ""),  # nothing usable left: keep the original name
        ('bad<>:"/|?*chars', "badchars"),
        ("trailing dot.", "trailing dot"),
        ("trailing space ", "trailing space"),
    ],
)
def test_clean_stem(typed, expected):
    assert clean_stem(typed) == expected


@pytest.mark.parametrize("name", ["CON", "nul", "COM1", "LPT9"])
def test_device_names_are_defused(name):
    """Windows cannot create a file called CON; it fails in a baffling way."""
    assert clean_stem(name) not in {"CON", "NUL", "COM1", "LPT9", name.upper()}


def test_a_long_name_is_trimmed():
    assert len(clean_stem("x" * 400)) <= 150


@pytest.mark.parametrize(
    ("index", "total", "expected"),
    [
        (1, 1, "art"),  # a single file gets no number
        (1, 2, "art 1"),
        (2, 2, "art 2"),
        (9, 10, "art 09"),  # padded so 10 does not sort before 9
        (10, 10, "art 10"),
        (7, 100, "art 007"),
    ],
)
def test_numbered_stem(index, total, expected):
    assert numbered_stem("art", index, total) == expected


def test_rename_output_keeps_the_extension(tmp_path):
    src = tmp_path / "IMG_0042.webp"
    src.write_bytes(b"x")
    out = rename_output(src, "holiday")
    assert out.name == "holiday.webp"
    assert out.exists() and not src.exists()


def test_rename_output_never_clobbers(tmp_path):
    (tmp_path / "taken.webp").write_bytes(b"old")
    src = tmp_path / "new.webp"
    src.write_bytes(b"new")
    out = rename_output(src, "taken")
    assert out.name == "taken (2).webp"
    assert (tmp_path / "taken.webp").read_bytes() == b"old"


# --- through the job runner -------------------------------------------------- #


def _drain(runner, timeout=60):
    end = time.time() + timeout
    while runner.busy and time.time() < end:
        time.sleep(0.02)
    events = []
    with contextlib.suppress(Exception):
        while True:
            events.append(runner.events.get_nowait())
    return events


def _png(path, size=(40, 30)):
    Image.new("RGB", size, (90, 140, 200)).save(path)
    return path


def test_a_batch_is_numbered_not_overwritten(tmp_path):
    files = [_png(tmp_path / f"shot{n}.png") for n in range(1, 4)]
    out = tmp_path / "out"
    runner = JobRunner()
    runner.start(files, convert_file, rename="holiday", out_dir=out, target="webp")
    _drain(runner)
    assert sorted(p.name for p in out.iterdir()) == [
        "holiday 1.webp",
        "holiday 2.webp",
        "holiday 3.webp",
    ]


def test_one_file_gets_the_bare_name(tmp_path):
    out = tmp_path / "out"
    runner = JobRunner()
    runner.start(
        [_png(tmp_path / "shot.png")], convert_file, rename="holiday", out_dir=out, target="webp"
    )
    _drain(runner)
    assert [p.name for p in out.iterdir()] == ["holiday.webp"]


def test_no_rename_keeps_the_original_name(tmp_path):
    out = tmp_path / "out"
    runner = JobRunner()
    runner.start([_png(tmp_path / "shot.png")], convert_file, out_dir=out, target="webp")
    _drain(runner)
    assert [p.name for p in out.iterdir()] == ["shot.webp"]


def test_the_result_reports_the_renamed_path(tmp_path):
    """The log and the "open folder" button must point at the real file."""
    out = tmp_path / "out"
    runner = JobRunner()
    runner.start(
        [_png(tmp_path / "shot.png")], convert_file, rename="holiday", out_dir=out, target="webp"
    )
    results = [payload for kind, payload in _drain(runner) if kind == "result"]
    assert results[0].output.name == "holiday.webp"
    assert results[0].output.exists()
