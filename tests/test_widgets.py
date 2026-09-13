"""Widget behaviour tests.

These exist because of a real bug: `AccessibleButton` defined `_on_enter` and
`_on_leave`, which are the names CTkButton uses internally. The subclass
silently overrode them, so `self._mouse_inside` was never set, and CTkButton's
`_on_release` checks that flag before calling the command. Every button in the
app looked and hovered correctly and did nothing when clicked. The GUI smoke
test missed it because it called `make_job()` directly and never clicked
anything.
"""

from __future__ import annotations

import contextlib
import time

import customtkinter as ctk
import pytest

from convertall.theme import DARK
from convertall.widgets import AccessibleButton


def test_accessible_button_does_not_shadow_ctk_internals():
    """No display needed, and it is the check that would have caught the bug.

    Anything private defined on both classes means the subclass is overriding
    behaviour the parent relies on - almost always by accident.
    """

    def private(cls):
        # Dunders like __doc__ exist on every class; only single-underscore
        # names represent behaviour one class can steal from another.
        return {n for n in vars(cls) if n.startswith("_") and not n.startswith("__")}

    ours, theirs = private(AccessibleButton), private(ctk.CTkButton)
    collisions = ours & theirs
    assert not collisions, (
        f"AccessibleButton shadows CTkButton internals: {sorted(collisions)}. "
        "Rename them - overriding a parent's private method breaks it silently."
    )


@pytest.fixture
def root():
    """A real Tk root, or skip. Headless CI has no display.

    Per-test rather than shared: these tests fire focus and hover events, and
    leftover widgets from an earlier test steal them. Creating roots in quick
    succession occasionally fails on Windows, so retry once before skipping -
    a test that silently skips is protecting nothing.
    """
    window = _new_root()
    window.geometry("400x200+50+50")
    yield window
    with contextlib.suppress(Exception):
        window.destroy()


def _new_root(attempts: int = 3):
    last = None
    for _ in range(attempts):
        try:
            return ctk.CTk()
        except Exception as exc:  # pragma: no cover - depends on environment
            last = exc
            time.sleep(0.4)
    pytest.skip(f"no display available: {last}")


def _click(button, window):
    """Drive the exact path CTkButton uses for a real mouse click.

    `_on_release` only fires the command when `_mouse_inside` is true, which the
    parent's `<Enter>` handler sets - so the Enter event is the part that
    matters here, not the release.
    """
    button._canvas.event_generate("<Enter>")
    window.update()
    button._canvas.event_generate("<ButtonRelease-1>")
    window.update()


def test_clicking_a_button_runs_its_command(root):
    fired = []
    button = AccessibleButton(root, DARK, "Go", lambda: fired.append(1))
    button.pack(padx=20, pady=20)
    root.update()

    _click(button, root)

    assert fired == [1], "a click must reach the command"


def test_a_disabled_button_ignores_clicks(root):
    fired = []
    button = AccessibleButton(root, DARK, "Go", lambda: fired.append(1))
    button.pack(padx=20, pady=20)
    button.configure(state="disabled")
    root.update()

    _click(button, root)

    assert fired == []


@pytest.mark.parametrize("variant", ["primary", "secondary", "quiet", "danger"])
def test_every_variant_is_clickable(root, variant):
    fired = []
    button = AccessibleButton(root, DARK, "Go", lambda: fired.append(1), variant=variant)
    button.pack(padx=20, pady=20)
    root.update()

    _click(button, root)

    assert fired == [1], f"{variant} buttons must be clickable"


def test_a_selected_nav_button_is_still_clickable(root):
    """set_active rewrites colours; it must not break the click path."""
    fired = []
    button = AccessibleButton(root, DARK, "Tool", lambda: fired.append(1), variant="secondary")
    button.pack(padx=20, pady=20)
    button.set_active(True)
    root.update()

    _click(button, root)

    assert fired == [1]


def test_focus_ring_survives_a_mouse_pass(root):
    """Hover must not paint over the keyboard focus ring."""
    button = AccessibleButton(root, DARK, "Go", lambda: None, variant="secondary")
    button.pack(padx=20, pady=20)
    root.update()

    button._canvas.event_generate("<FocusIn>")
    root.update()
    assert button.cget("border_color") == DARK.focus

    button._canvas.event_generate("<Enter>")
    root.update()
    assert button.cget("border_color") == DARK.focus, "hover overwrote the focus ring"

    button._canvas.event_generate("<Leave>")
    root.update()
    assert button.cget("border_color") == DARK.focus, "leaving cleared the focus ring"
