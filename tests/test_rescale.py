"""Changing a video's resolution, and the advice that goes with it.

The advice exists because the controls make two bad ideas easy: enlarging a
video (which cannot add detail) and shrinking one past the point where its
text is readable. Both produce a file that looks fine in a file listing.
"""

from __future__ import annotations

import pytest

from convertall.core.media import (
    RESOLUTIONS_OUT,
    rescale_advice,
    scale_filter,
)

# --- the filter -------------------------------------------------------------- #


def test_downscale_only_is_capped_in_the_filter():
    """Capping in-filter means a mixed batch is handled per file, not per batch."""
    assert scale_filter(720, upscale=False) == "scale=-2:'min(ih,720)':flags=lanczos"


def test_upscaling_asks_for_the_height_outright():
    assert scale_filter(1440, upscale=True) == "scale=-2:'1440':flags=lanczos"


def test_width_is_always_even():
    """yuv420p cannot store an odd width; -2 rounds it and keeps the aspect."""
    assert scale_filter(480, upscale=False).startswith("scale=-2:")


# --- the advice -------------------------------------------------------------- #


def test_no_advice_without_a_known_source():
    assert rescale_advice(0) == ""


def test_a_source_with_no_choice_yet_gets_the_range():
    note = rescale_advice(1080)
    assert "480p" in note and "2160p" in note


@pytest.mark.parametrize(
    ("source", "target", "floor"),
    [
        (1080, 360, "480p"),
        (720, 360, "480p"),
        (2160, 480, "720p"),  # a 4K source should not be cut to 480p
    ],
)
def test_downscaling_too_far_is_called_out(source, target, floor):
    note = rescale_advice(source, target)
    assert note.startswith("Note: it is not recommended to downscale below")
    assert floor in note
    assert f"starting resolution of {source}p" in note


@pytest.mark.parametrize(("source", "target"), [(1080, 720), (1080, 480), (720, 480)])
def test_sensible_downscales_are_not_nagged(source, target):
    assert not rescale_advice(source, target).startswith("Note:")


def test_upscaling_far_past_the_source_is_called_out():
    note = rescale_advice(720, 2160, upscale=True)
    assert note.startswith("Note: it is not recommended to upscale above 1440p")
    assert "starting resolution of 720p" in note


def test_a_modest_upscale_is_allowed_but_still_honest():
    note = rescale_advice(720, 1440, upscale=True)
    assert not note.startswith("Note:")
    assert "softer" in note


def test_advice_only_names_heights_the_menu_offers():
    """Advising a height the dropdown does not contain would be useless."""
    offered = {f"{h}p" for h in RESOLUTIONS_OUT if h}
    for source in (360, 480, 720, 1080, 1440, 2160):
        words = rescale_advice(source).replace(",", " ").replace(".", " ").split()
        named = {w for w in words if w.endswith("p") and w[:-1].isdigit()}
        assert named <= offered | {f"{source}p"}
