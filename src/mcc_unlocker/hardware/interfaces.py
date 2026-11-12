"""Minimal ADB contracts used by the guided workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class AdbTarget:
    serial: str
    transport: str
    host: str | None = None
    port: int | None = None
    state: str = "device"

    @property
    def is_authorized(self) -> bool:
        return self.state == "device"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    async def run(self, args: Sequence[str], *, timeout: float = 60.0) -> ProcessResult: ...


__all__ = ["AdbTarget", "ProcessResult", "ProcessRunner"]
