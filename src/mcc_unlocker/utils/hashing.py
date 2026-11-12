"""Streaming SHA-256 helpers. Never load a 16 MiB boot image several times."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import BinaryIO, Iterable

CHUNK_SIZE = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(stream: BinaryIO, *, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = CHUNK_SIZE) -> str:
    with open(path, "rb") as handle:
        return sha256_stream(handle, chunk_size=chunk_size)


def sha256_chunks(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


class StreamingHasher:
    """Incremental hasher with size accounting, used by backup streaming."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._size = 0

    def update(self, chunk: bytes) -> None:
        self._digest.update(chunk)
        self._size += len(chunk)

    @property
    def size(self) -> int:
        return self._size

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()

    def verify(self, expected: str) -> bool:
        return constant_time_compare(self.hexdigest, expected)


def hash_parts(parts: Iterable[bytes]) -> str:
    return sha256_chunks(parts)
