"""Build the window, exercise it, and save screenshots for the README.

Run from the project root:  python tools/screenshot.py

Doubles as a GUI smoke test - it constructs every panel, switches tools,
rebuilds the window for both palettes and fails loudly on any exception.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from convertall.app import PANELS, ConvertAllApp  # noqa: E402

OUT = ROOT / "assets"


def settle(app, cycles: int = 12) -> None:
    for _ in range(cycles):
        app.update_idletasks()
        app.update()
        time.sleep(0.05)


def capture(app, name: str) -> Path:
    """Grab the window.

    ImageGrab takes a *screen region*, not a window, so anything overlapping
    the app gets photographed instead. Forcing topmost for the grab is what
    stops a stray window ending up in the README.
    """
    settle(app)
    app.attributes("-topmost", True)
    app.lift()
    app.focus_force()
    settle(app, 8)

    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))

    app.attributes("-topmost", False)

    if not _looks_like_convertall(shot):
        debug = Path(tempfile.gettempdir()) / f"convertall-bad-grab-{name}"
        shot.save(debug)
        raise SystemExit(
            f"{name}: the grab does not look like ConvertAll - another window was "
            f"probably in front. Nothing saved to assets/.\nThe rejected image is at "
            f"{debug} if you want to check whether the capture or the check is wrong."
        )

    path = OUT / name
    shot.save(path)
    print(f"  saved {path.relative_to(ROOT)}  ({shot.width}x{shot.height})")
    return path


def _looks_like_convertall(shot) -> bool:
    """Cheap sanity check before an image is written into assets/.

    ImageGrab takes a screen region, so a window that steals focus mid-run gets
    photographed instead - and that image would go straight into the README of
    a public repo. Two cheap signals together are enough to catch it: a dark
    strip along the very top of the window, and a meaningful amount of the
    amber accent (the wordmark plus the selected tool button). Sampling any
    lower than the top few pixels runs through the wordmark itself, which is
    exactly the false negative this replaced.
    """
    rgb = shot.convert("RGB")
    width, height = rgb.size
    if width < 200 or height < 200:
        return False

    band_y = max(2, int(height * 0.01))
    strip = [rgb.getpixel((x, band_y)) for x in range(5, width, max(1, width // 30))]
    dark_top = sum(1 for r, g, b in strip if r < 70 and g < 70 and b < 80) >= len(strip) * 0.8

    small = rgb.resize((160, 100))
    accent = sum(1 for r, g, b in small.getdata() if r > 200 and g > 170 and b < 120)

    return dark_top and accent > 40


def sample_files() -> list[str]:
    """A handful of throwaway files so the screenshots show a real workflow."""
    import tempfile

    from PIL import Image

    folder = Path(tempfile.mkdtemp(prefix="convertall-demo-"))
    names = ["product-hero", "brand-mark", "icon-source", "banner-wide", "team-photo"]
    made = []
    for index, name in enumerate(names):
        img = Image.new("RGBA", (400 + index * 60, 300), (0, 0, 0, 0))
        for x in range(40, img.width - 40):
            for y in range(40, 260):
                img.putpixel((x, y), ((x * 3) % 256, (y * 5) % 256, 180, 255))
        path = folder / f"{name}.png"
        img.save(path)
        made.append(str(path))
    return made


def main() -> int:
    OUT.mkdir(exist_ok=True)
    app = ConvertAllApp()
    app.geometry("1180x860+60+20")
    settle(app)

    print("Panels built:")
    for cls in PANELS:
        app.select_tool(cls.key)
        settle(app, 4)
        worker, kwargs = app.panels[cls.key].make_job()
        print(f"  {cls.key:<11} {worker.__name__}({', '.join(kwargs)})")

    demo = sample_files()
    for key in ("conversion", "trace"):
        app.panels[key]._ingest(demo)
    settle(app)

    app.select_tool("conversion")
    capture(app, "screenshot-conversion.png")

    app.select_tool("trace")
    capture(app, "screenshot-trace.png")

    print("Rebuilding for maximum contrast + 130% text…")
    app.toggle_palette()
    app.set_scale(1.3)
    settle(app)
    app.select_tool("split")
    capture(app, "screenshot-maximum-contrast.png")

    print("Restoring defaults…")
    app.toggle_palette()
    app.set_scale(1.0)
    settle(app)

    app.destroy()
    print("GUI smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
