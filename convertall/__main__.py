"""Entry point: `python -m convertall` or the `convertall` console script."""

from __future__ import annotations

import argparse
import sys

from . import __version__

REQUIRED = {
    "customtkinter": "customtkinter",
    "PIL": "Pillow",
    "lxml": "lxml",
}


def _missing() -> list[str]:
    import importlib.util

    return [
        package for module, package in REQUIRED.items() if importlib.util.find_spec(module) is None
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="convertall",
        description=(
            "Accessible batch conversion for images (includes vector art), audio, and video."
        ),
    )
    parser.add_argument("--version", action="version", version=f"ConvertAll {__version__}")
    parser.add_argument(
        "--contrast",
        choices=["dark", "maximum"],
        default="dark",
        help="Start with this palette (default: dark).",
    )
    parser.add_argument(
        "--text-scale",
        type=float,
        default=1.0,
        metavar="FACTOR",
        help="Start with this text scale, 0.85 to 1.6 (default: 1.0).",
    )
    args = parser.parse_args(argv)

    missing = _missing()
    if missing:
        print("ConvertAll is missing required packages:", file=sys.stderr)
        for package in missing:
            print(f"  - {package}", file=sys.stderr)
        print("\nInstall them with:\n    pip install -r requirements.txt", file=sys.stderr)
        return 1

    from .app import ConvertAllApp

    app = ConvertAllApp(palette_key=args.contrast, scale=args.text_scale)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
