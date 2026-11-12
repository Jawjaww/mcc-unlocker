#!/usr/bin/env python3
"""Build the Windows desktop application with PyInstaller.

Run this on Windows (or in the Windows CI job). PyInstaller does not
cross-compile from macOS.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "mcc_unlocker" / "__main__.py"


def build_command(*, onefile: bool, console: bool) -> list[str]:
    separator = ";" if platform.system() == "Windows" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "MCC-Unlocker",
        "--add-data",
        f"{ROOT / 'assets'}{separator}assets",
        "--add-data",
        f"{ROOT / 'docs'}{separator}docs",
        "--hidden-import",
        "mcc_unlocker.ui.unlock_app",
        "--hidden-import",
        "mcc_unlocker.ui.launcher_app",
    ]
    if onefile:
        command.append("--onefile")
    if not console:
        command.append("--windowed")
    command.append(str(ENTRY))
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--onefile", action="store_true")
    parser.add_argument("--console", action="store_true")
    args = parser.parse_args(argv)
    command = build_command(onefile=args.onefile, console=args.console)
    if args.dry_run:
        print(" ".join(command))
        print("Dry run OK: no binary produced.")
        return 0
    if platform.system() != "Windows":
        print("Refus : construis l'exécutable Windows depuis Windows ou la CI.", file=sys.stderr)
        return 2
    if not ENTRY.is_file():
        print(f"Entrée introuvable : {ENTRY}", file=sys.stderr)
        return 2
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
