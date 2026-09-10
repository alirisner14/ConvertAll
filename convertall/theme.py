"""High-contrast dark palettes.

Every foreground/background pair below was chosen to clear WCAG 2.1 AA (4.5:1)
for body text, and most clear AAA (7:1). Approximate contrast ratios against
the page background are noted inline so future edits keep the guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    key: str
    label: str
    bg: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    on_accent: str
    focus: str
    success: str
    warning: str
    error: str


DARK = Palette(
    key="dark",
    label="High-contrast dark",
    bg="#0A0E14",  # near-black page
    surface="#141C26",  # cards
    surface_alt="#1E2936",  # inputs, list rows
    border="#4A5D75",
    border_strong="#7C93AE",
    text="#FFFFFF",  # 19.5:1 on bg  (AAA)
    text_muted="#C7D3E0",  # 12.9:1 on bg  (AAA)
    accent="#FFD60A",  # 14.4:1 on bg  (AAA)
    accent_hover="#FFE97A",
    on_accent="#0A0E14",  # 14.4:1 on accent
    focus="#5CE1FF",  # cyan focus ring, distinct from the amber accent
    success="#5BE49B",  # 12.0:1 on bg
    warning="#FFB020",
    error="#FF8A80",  # 8.9:1 on bg
)

MAXIMUM = Palette(
    key="maximum",
    label="Maximum contrast",
    bg="#000000",
    surface="#000000",
    surface_alt="#0D0D0D",
    border="#FFFFFF",
    border_strong="#FFFFFF",
    text="#FFFFFF",  # 21:1 - the highest possible
    text_muted="#FFFFFF",
    accent="#FFFF00",  # 19.6:1
    accent_hover="#FFFFFF",
    on_accent="#000000",
    focus="#00FFFF",
    success="#00FF7F",
    warning="#FFFF00",
    error="#FF6E6E",
)

PALETTES: dict[str, Palette] = {p.key: p for p in (DARK, MAXIMUM)}

# Type scale. The app can step every size up or down together (Ctrl +/-) so the
# whole interface scales for low-vision users without breaking the layout.
BASE_SIZES = {
    "display": 26,
    "title": 19,
    "body": 15,
    "small": 13,
    "mono": 13,
}
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"

MIN_SCALE, MAX_SCALE, SCALE_STEP = 0.85, 1.6, 0.1


def sized(name: str, scale: float = 1.0) -> int:
    return max(10, round(BASE_SIZES[name] * scale))
