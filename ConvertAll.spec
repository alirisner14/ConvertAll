# PyInstaller build spec.
#   pyinstaller --noconfirm ConvertAll.spec
#
# Produces dist/ConvertAll/ containing ConvertAll.exe. The FFmpeg binary that
# ships inside imageio-ffmpeg is collected too, so the build runs on a machine
# with no FFmpeg installed.

from PyInstaller.utils.hooks import collect_data_files

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]
datas += collect_data_files("imageio_ffmpeg")
datas += collect_data_files("customtkinter")
datas += collect_data_files("tkinterdnd2")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder", "pillow_heif", "potrace"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ConvertAll",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI app - no console window
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ConvertAll",
)
