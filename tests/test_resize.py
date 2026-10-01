"""The custom resize field.

A typo in a pixel box must not quietly become "keep the original size" - that
produces files the user did not ask for and no visible complaint, which is the
worst of both. So the resolver either returns a number or raises something
worth showing.
"""

from __future__ import annotations

import contextlib
import time

import pytest

from convertall.app import CUSTOM_SIZE, KEEP_SIZE, ConvertAllApp


@pytest.fixture(scope="module")
def panel():
    window = None
    last = None
    for _ in range(3):
        try:
            window = ConvertAllApp()
            break
        except Exception as exc:  # pragma: no cover - depends on environment
            last = exc
            time.sleep(0.4)
    if window is None:
        pytest.skip(f"no display available: {last}")
    for _ in range(4):
        window.update_idletasks()
        window.update()
    yield window.panels["conversion"]
    with contextlib.suppress(Exception):
        window.destroy()


def _resolve(panel, choice, typed=""):
    panel.resize.set(choice)
    panel.custom_px.set(typed)
    return panel._max_dimension()


def test_keep_original_means_no_resize(panel):
    assert _resolve(panel, KEEP_SIZE) is None


def test_a_preset_size_is_read_as_pixels(panel):
    assert _resolve(panel, "2048 px") == 2048


@pytest.mark.parametrize("typed", ["900", " 900 ", "900px", "900 PX"])
def test_custom_accepts_the_ways_people_type_it(panel, typed):
    assert _resolve(panel, CUSTOM_SIZE, typed) == 900


@pytest.mark.parametrize("typed", ["", "big", "12.5", "4", "99999", "-800"])
def test_custom_refuses_what_it_cannot_honour(panel, typed):
    with pytest.raises(ValueError):
        _resolve(panel, CUSTOM_SIZE, typed)


def test_the_pixel_field_is_only_shown_for_custom(panel):
    """winfo_manager, not winfo_ismapped: the whole row is hidden unless an
    image target is selected, so being mapped is not what is under test."""
    panel.resize.set(KEEP_SIZE)
    panel._toggle_custom_size()
    assert panel.custom_entry.winfo_manager() == ""

    panel.resize.set(CUSTOM_SIZE)
    panel._toggle_custom_size()
    assert panel.custom_entry.winfo_manager() == "pack"
