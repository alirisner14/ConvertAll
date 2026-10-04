"""Build the standalone Windows executable locally.

    python tools/build_exe.py                 # build
    python tools/build_exe.py --clean         # wipe build/ and dist/ first
    python tools/build_exe.py --smoke         # build, then launch it and check it starts
    python tools/build_exe.py --install       # also replace the copy you launch
    python tools/build_exe.py --clean --smoke # what CI effectively does, plus the launch

Output lands in dist/ConvertAll/ConvertAll.exe. Both build/ and dist/ are
gitignored. This uses the same ConvertAll.spec the release workflow uses, so a
green run here means the tagged release should build too.

--install then replaces the copy you actually launch - by default a ConvertAll
folder on the desktop - so a rebuild refreshes it and a stale build cannot sit
there pretending to be current. Override the destination with --install-dir or
the CONVERTALL_INSTALL_DIR environment variable.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "ConvertAll"
WORK = ROOT / "build" / "ConvertAll"
EXE = DIST / "ConvertAll.exe"

# Pure-Python packages live inside the frozen PYZ archive, not on disk. Looking
# for them as files reports a false "missing", so check the archive's own table
# of contents instead.
FROZEN_MODULES = ("potrace", "convertall.core.vectorize", "convertall.app")
BUNDLED_FILES = ("imageio_ffmpeg",)


def desktop_dir() -> Path:
    """Where the desktop actually is, which is not always ~/Desktop.

    A machine that once had OneDrive keeps its desktop redirected to
    ~/OneDrive/Desktop long after OneDrive is gone, so ask Windows rather than
    assuming - guessing wrong would install to a folder nobody looks at.
    """
    if sys.platform == "win32":
        try:
            from uuid import UUID

            desktop = UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
            guid = (ctypes.c_byte * 16).from_buffer_copy(desktop.bytes_le)
            out = ctypes.c_wchar_p()
            ok = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(out)
            )
            if ok == 0 and out.value:
                return Path(out.value)
        except Exception:  # pragma: no cover - falls through to the guess
            pass
    return Path.home() / "Desktop"


def install_dir() -> Path:
    override = os.environ.get("CONVERTALL_INSTALL_DIR")
    return Path(override).expanduser() if override else desktop_dir() / "ConvertAll"


def install(target: Path) -> list[str]:
    """Replace the installed copy with the build that was just verified.

    Refuses any folder that does not already look like a ConvertAll install:
    this deletes its destination, and a mistyped path must not cost somebody
    their documents.
    """
    if target.exists():
        if not target.is_dir():
            return [f"{target} exists and is not a folder"]
        held = [item.name for item in target.iterdir()]
        if held and "ConvertAll.exe" not in held:
            return [
                f"{target} is not empty and holds no ConvertAll.exe - refusing to "
                "overwrite it. Use --install-dir to point somewhere else."
            ]
        print(f"\nreplacing the installed copy at {target}...")
        try:
            shutil.rmtree(target)
        except PermissionError:
            return [f"{target} is in use - close ConvertAll and run this again"]
    else:
        print(f"\ninstalling to {target}...")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DIST, target)
    return []


def fail(message: str) -> int:
    print(f"\nFAILED: {message}", file=sys.stderr)
    return 1


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def preflight() -> str | None:
    if sys.platform != "win32":
        print(
            f"note: building on {sys.platform}; PyInstaller targets the host OS, "
            "so this produces a native binary rather than a Windows .exe."
        )
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        return "PyInstaller is not installed. Run:\n    pip install -r requirements-dev.txt"
    if not (ROOT / "ConvertAll.spec").exists():
        return "ConvertAll.spec is missing from the project root."
    return None


def ensure_icon() -> None:
    if (ROOT / "assets" / "icon.ico").exists():
        return
    print("assets/icon.ico missing - generating it first…")
    sys.path.insert(0, str(ROOT))
    from tools.make_icon import build

    build()


def clean() -> None:
    for folder in (ROOT / "build", ROOT / "dist"):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            print(f"removed {folder.relative_to(ROOT)}/")


def build() -> int:
    print("running PyInstaller…\n")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "ConvertAll.spec"],
        cwd=ROOT,
    )
    return result.returncode


def verify() -> list[str]:
    """Check the bundle actually contains what the app needs at runtime."""
    problems: list[str] = []

    if not EXE.exists():
        return [f"{EXE.relative_to(ROOT)} was not produced"]

    toc = WORK / "PYZ-00.toc"
    if toc.exists():
        frozen = toc.read_text(encoding="utf-8", errors="replace")
        for module in FROZEN_MODULES:
            if f"'{module}'" not in frozen:
                problems.append(f"{module} is not in the frozen archive")
    else:
        problems.append(f"{toc.relative_to(ROOT)} not found - cannot verify frozen modules")

    for name in BUNDLED_FILES:
        if not any(DIST.rglob(f"*{name}*")):
            problems.append(f"{name} data files are missing from the bundle")

    if not any(DIST.rglob("ffmpeg*.exe")) and not any(DIST.rglob("ffmpeg*")):
        problems.append("no bundled FFmpeg binary found")

    return problems


def smoke(seconds: int = 8) -> list[str]:
    """Launch the built app, confirm it stays up, then close it."""
    print(f"\nlaunching {EXE.name} for {seconds}s…")
    proc = subprocess.Popen([str(EXE)], cwd=DIST)
    time.sleep(seconds)
    if proc.poll() is not None:
        return [f"the app exited on its own with code {proc.returncode}"]
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("app started and was closed cleanly")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ConvertAll executable.")
    parser.add_argument("--clean", action="store_true", help="remove build/ and dist/ first")
    parser.add_argument("--smoke", action="store_true", help="launch the result to check it starts")
    parser.add_argument("--skip-verify", action="store_true", help="skip the bundle checks")
    parser.add_argument(
        "--install",
        action="store_true",
        help="replace the installed copy with this build",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        help="where --install puts it; overrides CONVERTALL_INSTALL_DIR",
    )
    args = parser.parse_args(argv)

    problem = preflight()
    if problem:
        return fail(problem)

    ensure_icon()
    if args.clean:
        clean()

    code = build()
    if code != 0:
        return fail(f"PyInstaller exited with {code}")

    problems: list[str] = []
    if not args.skip_verify:
        print("\nverifying the bundle…")
        problems += verify()
        for line in problems:
            print(f"  - {line}")
        if not problems:
            print("  all expected contents present")

    if args.smoke and not problems:
        problems += smoke()
        for line in problems:
            print(f"  - {line}")

    # Only ever install a build that passed its checks: replacing a working
    # copy with a broken one is worse than not installing at all.
    installed: Path | None = None
    if args.install and not problems:
        installed = args.install_dir or install_dir()
        problems += install(installed)
        for line in problems:
            print(f"  - {line}")

    if problems:
        return fail(f"{len(problems)} problem(s) with the build")

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print("\nBuild complete.")
    print(f"  executable   {EXE}")
    print(f"  exe size     {human(EXE.stat().st_size)}")
    print(f"  bundle size  {human(total)}")
    if installed:
        print(f"  installed    {installed}")
    launch = (installed / "ConvertAll.exe") if installed else EXE
    print(f"\nRun it with:\n  {launch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
