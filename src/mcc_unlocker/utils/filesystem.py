"""Atomic filesystem primitives and small path helpers."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator


class AtomicWriteError(OSError):
    """Raised when an atomic write cannot be completed."""


def ensure_dir(path: Path | str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def atomic_write_bytes(path: Path | str, data: bytes, *, mode: int = 0o644) -> Path:
    """Write ``data`` to ``path`` atomically (same-directory temp + rename)."""
    destination = Path(path)
    ensure_dir(destination.parent)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    tmp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, destination)
        _fsync_dir(destination.parent)
        return destination
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path | str, payload: Any, *, indent: int = 2) -> Path:
    text = json.dumps(payload, indent=indent, sort_keys=True, ensure_ascii=False) + "\n"
    return atomic_write_text(path, text)


def read_json(path: Path | str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _fsync_dir(directory: Path) -> None:
    if os.name == "nt":  # directory fsync is not available on Windows
        return
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def free_space_bytes(path: Path | str) -> int:
    target = Path(path)
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        return shutil.disk_usage(target).free
    except OSError:
        return 0


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"  # pragma: no cover


def safe_join(root: Path | str, *parts: str) -> Path:
    """Join and refuse traversal outside ``root``."""
    base = Path(root).resolve()
    candidate = base.joinpath(*parts).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("path escapes root")
    return candidate


def iter_files(root: Path | str) -> Iterator[Path]:
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            yield path


def directory_size(path: Path | str) -> int:
    return sum(item.stat().st_size for item in iter_files(path))
