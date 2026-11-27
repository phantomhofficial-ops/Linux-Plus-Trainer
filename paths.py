"""Cross-platform and PyInstaller bundle-safe path resolution helpers."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """Return True when running inside a frozen bundle (e.g. PyInstaller)."""
    return bool(getattr(sys, "_MEIPASS", None)) or bool(getattr(sys, "frozen", False))


def get_resource_path(relative_path: str | Path = "") -> Path:
    """Resolve a read-only bundled asset path using sys._MEIPASS when frozen."""
    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass) if meipass else PROJECT_ROOT
    if relative_path:
        return base / relative_path
    return base


def get_user_data_dir(*, create: bool = True) -> Path:
    """Return the writable user data directory for progress persistence.

    When running from source (not frozen), returns ``PROJECT_ROOT / "data"`` so
    existing local ``data/progress.json`` and tests remain intact. When frozen,
    returns the OS-standard application data directory and optionally creates it.
    """
    if not is_frozen():
        target = PROJECT_ROOT / "data"
    elif sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / "LinuxPlusTrainer"
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        target = base / "LinuxPlusTrainer"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else (Path.home() / ".local" / "share")
        target = base / "linux-plus-trainer"

    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_questions_dir() -> Path:
    """Return the path to bundled question JSON files."""
    return get_resource_path(Path("data") / "questions")


def get_templates_dir() -> Path:
    """Return the path to bundled Flask HTML templates."""
    return get_resource_path("templates")


def get_static_dir() -> Path:
    """Return the path to bundled Flask static assets."""
    return get_resource_path("static")


def get_progress_file(
    progress_path: Path | str | None = None,
    *,
    create_dir: bool = True,
) -> Path:
    """Return an explicit progress_path override or the OS-native progress.json path."""
    if progress_path is not None:
        return Path(progress_path)
    return get_user_data_dir(create=create_dir) / "progress.json"
