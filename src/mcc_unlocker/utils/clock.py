"""Injectable clock and async sleep, so timeout logic is testable in microseconds."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...
    def monotonic(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        await asyncio.sleep(seconds)


class FakeClock:
    """Virtual clock; ``sleep`` advances time immediately."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 10, 27, 0, 0, 0, tzinfo=timezone.utc)
        self._monotonic = 0.0
        self.sleeps: list[float] = []
        self.advance(0)

    def now_utc(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)
        self._monotonic += seconds

    @property
    def sleeps_total(self) -> float:
        return sum(self.sleeps)
