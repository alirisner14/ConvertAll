"""The palettes carry the project's accessibility claim, so measure them.

A colour tweak that looks fine on one monitor can quietly drop text below the
legibility threshold. These tests make that a build failure instead.
"""

from __future__ import annotations

import colorsys

import pytest

from convertall.theme import PALETTES, Palette, contrast_ratio, relative_luminance

AA_TEXT = 4.5  # WCAG 2.1 AA, body text
AAA_TEXT = 7.0  # WCAG 2.1 AAA, body text
AA_NON_TEXT = 3.0  # WCAG 2.1 AA, UI components and graphical objects

ALL = list(PALETTES.values())
IDS = [p.key for p in ALL]


def test_contrast_maths_matches_known_values():
    """Anchor the helper against pairs whose ratios are defined by the spec."""
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#000000", "#000000") == pytest.approx(1.0, abs=0.01)
    assert contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.02)
    # Order must not matter.
    assert contrast_ratio("#1B1C1E", "#ECEDEF") == contrast_ratio("#ECEDEF", "#1B1C1E")
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=0.001)


@pytest.mark.parametrize("palette", ALL, ids=IDS)
def test_body_text_clears_aaa_on_every_surface(palette: Palette):
    for surface in (palette.bg, palette.surface, palette.surface_alt):
        assert contrast_ratio(palette.text, surface) >= AAA_TEXT, (
            f"{palette.key}: body text on {surface}"
        )


@pytest.mark.parametrize("palette", ALL, ids=IDS)
def test_muted_text_clears_aaa_on_every_surface(palette: Palette):
    """Help text is where a palette usually cheats. It must not."""
    for surface in (palette.bg, palette.surface, palette.surface_alt):
        assert contrast_ratio(palette.text_muted, surface) >= AAA_TEXT, (
            f"{palette.key}: muted text on {surface}"
        )


@pytest.mark.parametrize("palette", ALL, ids=IDS)
def test_accent_is_legible_as_text_and_as_a_fill(palette: Palette):
    assert contrast_ratio(palette.accent, palette.bg) >= AAA_TEXT
    assert contrast_ratio(palette.accent, palette.surface_alt) >= AA_TEXT
    # Label printed on top of an accent-filled button.
    assert contrast_ratio(palette.on_accent, palette.accent) >= AAA_TEXT
    assert contrast_ratio(palette.on_accent, palette.accent_hover) >= AAA_TEXT


@pytest.mark.parametrize("palette", ALL, ids=IDS)
def test_ui_boundaries_clear_the_non_text_threshold(palette: Palette):
    """Borders and focus rings are graphical objects, not text: 3:1 applies."""
    assert contrast_ratio(palette.border_strong, palette.bg) >= AA_NON_TEXT
    assert contrast_ratio(palette.focus, palette.bg) >= AA_NON_TEXT
    assert contrast_ratio(palette.focus, palette.surface) >= AA_NON_TEXT


@pytest.mark.parametrize("palette", ALL, ids=IDS)
def test_status_colours_are_legible(palette: Palette):
    for colour in (palette.success, palette.warning, palette.error):
        assert contrast_ratio(colour, palette.bg) >= AA_TEXT
        assert contrast_ratio(colour, palette.surface_alt) >= AA_TEXT


def _hue(colour: str) -> float:
    """Hue angle in degrees."""
    h = colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def test_focus_is_distinguishable_from_the_accent():
    """Hover uses the accent, focus uses the ring. If they shared a hue, 'where
    am I' and 'what is under the mouse' would look the same.

    Contrast ratio cannot express this - two colours of similar lightness score
    about 1:1 however different they look. Hue separation is the real measure.
    """
    dark = PALETTES["dark"]
    gap = abs(_hue(dark.focus) - _hue(dark.accent))
    gap = min(gap, 360 - gap)
    assert gap >= 60, f"focus and accent are only {gap:.0f} degrees apart"


def test_maximum_contrast_really_is_maximum():
    maximum = PALETTES["maximum"]
    assert contrast_ratio(maximum.text, maximum.bg) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio(maximum.accent, maximum.bg) >= 15.0


def test_dark_palette_is_charcoal_not_pure_black_or_white():
    """The point of the default palette: easy on the eyes, still AAA."""
    dark = PALETTES["dark"]
    assert dark.bg not in ("#000000", "#FFFFFF")
    assert dark.text != "#FFFFFF", "pure white on dark glares; keep it off-white"
    # Charcoal, not a blue-black: the channels stay close together.
    h = dark.bg.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    assert max(r, g, b) - min(r, g, b) <= 12, "background has a colour cast"
