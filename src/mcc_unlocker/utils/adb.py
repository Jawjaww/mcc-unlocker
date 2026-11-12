"""Small ADB discovery helpers; no dependency on the legacy environment code."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def resolve_adb_path(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    candidates: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Android" / "platform-tools" / "adb.exe")
    candidates.extend(
        [
            Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
            Path.home() / "Android" / "Sdk" / "platform-tools" / "adb",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return "adb"


def list_adb_devices(adb_path: str, *, timeout: float = 20.0) -> list[tuple[str, str]]:
    try:
        result = subprocess.run(
            [adb_path, "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    devices: list[tuple[str, str]] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


__all__ = ["list_adb_devices", "resolve_adb_path"]
