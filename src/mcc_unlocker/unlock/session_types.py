"""Result payloads for the guided unlock session."""

from __future__ import annotations

from dataclasses import dataclass

from .twrp import SystemPatchResult


@dataclass(frozen=True, slots=True)
class SessionPatchResult:
    patch: SystemPatchResult
    verified_properties: dict[str, str]
    recovery_from_boot_removed: bool


@dataclass(frozen=True, slots=True)
class SessionPushResult:
    boot_remote: str
    recovery_remote: str
