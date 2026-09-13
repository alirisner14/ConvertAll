"""Layout guards.

Nothing in the window scrolls horizontally, so any content wider than the pane
is simply unreachable. That makes the minimum window size a correctness
constraint rather than a taste one: if a panel grows a wider control, the
minimum has to grow with it.
"""

from __future__ import annotations

import contextlib
import time

import pytest

from convertall.app import PANELS, ConvertAllApp


# Module-scoped: building a second Tk root immediately after destroying one is
# flaky on Windows, and a test that silently skips is protecting nothing.
@pytest.fixture(scope="module")
def app():
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
    for _ in range(6):
        window.update_idletasks()
        window.update()
    yield window
    with contextlib.suppress(Exception):
        window.destroy()


def _shrink_to_minimum(app):
    """Ask for something impossibly small; Tk clamps to the minimum."""
    app.geometry("1x1+20+20")
    for _ in range(10):
        app.update_idletasks()
        app.update()
    return app.winfo_width(), app.winfo_height()


def test_no_panel_is_clipped_at_the_minimum_window_size(app):
    _shrink_to_minimum(app)
    available = app.content.winfo_width()

    too_wide = {}
    for cls in PANELS:
        app.select_tool(cls.key)
        for _ in range(6):
            app.update_idletasks()
            app.update()
        needed = app.panels[cls.key].winfo_reqwidth()
        if needed > available:
            too_wide[cls.title] = (needed, available)

    assert not too_wide, (
        "these panels clip at the minimum window size, and nothing scrolls "
        f"horizontally, so the content is unreachable: {too_wide}. "
        "Raise the minsize width in ConvertAllApp, or narrow the panel."
    )


def test_the_primary_action_is_reachable_at_the_minimum_size(app):
    """The Convert button lives outside the scroll area for exactly this reason."""
    _shrink_to_minimum(app)
    for cls in PANELS:
        app.select_tool(cls.key)
        for _ in range(6):
            app.update_idletasks()
            app.update()
        button = app.panels[cls.key].run_button
        assert button.winfo_ismapped(), f"{cls.title}: run button is not visible"
        assert (
            button.winfo_rooty() + button.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        ), f"{cls.title}: run button sits below the bottom of the window"
