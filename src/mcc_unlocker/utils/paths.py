"""Resolve source and PyInstaller roots."""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def assets_dir() -> Path:
    return project_root() / "assets"


def unlock_assets_dir() -> Path:
    return assets_dir() / "unlock"


__all__ = ["assets_dir", "project_root", "unlock_assets_dir"]
