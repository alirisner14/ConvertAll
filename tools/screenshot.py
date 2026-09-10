"""Build the window, exercise it, and save screenshots for the README.

Run from the project root:  python tools/screenshot.py

Doubles as a GUI smoke test - it constructs every panel, switches tools,
rebuilds the window for both palettes and fails loudly on any exception.
"""

from __future__ import annotations

import sys
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
    settle(app)
    app.lift()
    app.focus_force()
    settle(app, 6)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    path = OUT / name
    shot.save(path)
    print(f"  saved {path.relative_to(ROOT)}  ({shot.width}x{shot.height})")
    return path


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
    for key in ("images", "trace"):
        app.panels[key]._ingest(demo)
    settle(app)

    app.select_tool("images")
    capture(app, "screenshot-images.png")

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
