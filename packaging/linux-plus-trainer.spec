# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CompTIA Linux+ (XK0-006 / V8) Study Trainer."""

from pathlib import Path
import sys

SPEC_DIR = Path(SPECPATH).resolve()
ROOT_DIR = SPEC_DIR.parent
ASSETS_DIR = SPEC_DIR / "assets"

if sys.platform == "win32":
    candidate_icon = ASSETS_DIR / "linux-plus-trainer.ico"
elif sys.platform == "darwin":
    candidate_icon = ASSETS_DIR / "linux-plus-trainer.icns"
else:
    candidate_icon = ASSETS_DIR / "linux-plus-trainer.png"

icon_path = str(candidate_icon) if candidate_icon.is_file() else None

datas = [
    (str(ROOT_DIR / "data" / "questions"), "data/questions"),
    (str(ROOT_DIR / "templates"), "templates"),
    (str(ROOT_DIR / "static"), "static"),
]

hiddenimports = [
    "app",
    "desktop_app",
    "engine",
    "labs",
    "paths",
    "sandbox",
    "web_app",
    "webview",
    "flask",
    "jinja2",
    "werkzeug",
    "rich",
]

a = Analysis(
    [str(ROOT_DIR / "app.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LinuxPlusTrainer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False if sys.platform in {"win32", "darwin"} else True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LinuxPlusTrainer",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="LinuxPlusTrainer.app",
        icon=icon_path,
        bundle_identifier="io.github.linuxplustrainer.LinuxPlusTrainer",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
