"""Pure, idempotent patcher for Android ``/system/build.prop``.

It preserves unrelated lines and comments, replaces existing keys instead of
duplicating them, and verifies the result. Filesystem/SELinux work lives in the
TWRP adapter, not here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result

#: Exact properties from the community reference, in canonical form.
PROPERTIES: tuple[tuple[str, str], ...] = (
    ("persist.service.adb.enable", "1"),
    ("persist.service.debuggable", "1"),
    ("persist.sys.usb.config", "mtp,adb"),
    ("qemu.hw.mainkeys", "0"),
)


@dataclass(frozen=True, slots=True)
class SystemPatch:
    original_sha256: str
    patched_sha256: str
    original: bytes
    patched: bytes
    properties: Mapping[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.original != self.patched

    def to_dict(self) -> dict[str, object]:
        return {
            "original_sha256": self.original_sha256,
            "patched_sha256": self.patched_sha256,
            "changed": self.changed,
            "properties": dict(self.properties),
        }


@dataclass
class SystemPatcher:
    properties: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType(dict(PROPERTIES))
    )

    def patch(self, original: bytes) -> Result[SystemPatch]:
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "build.prop is not valid UTF-8", "error": str(exc)},
            )
        expected = {str(key): str(value) for key, value in self.properties.items()}
        output: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key not in expected:
                output.append(line)
                continue
            # Replace only the first occurrence; drop later duplicates.
            if key in seen:
                continue
            output.append(f"{key}={expected[key]}")
            seen.add(key)
        for key, value in expected.items():
            if key not in seen:
                output.append(f"{key}={value}")
        patched_text = "\n".join(output).rstrip("\n") + "\n"
        patched = patched_text.encode("utf-8")
        return Ok(
            SystemPatch(
                original_sha256=hashlib.sha256(original).hexdigest(),
                patched_sha256=hashlib.sha256(patched).hexdigest(),
                original=original,
                patched=patched,
                properties=MappingProxyType(expected),
            )
        )

    def verify(self, content: bytes) -> Result[dict[str, str]]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "build.prop is not valid UTF-8", "error": str(exc)},
            )
        counts: dict[str, int] = {key: 0 for key in self.properties}
        values: dict[str, str] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in counts:
                counts[key] += 1
                values[key] = value.strip()
        errors: list[str] = []
        for key, expected in self.properties.items():
            if counts[key] != 1:
                errors.append(f"{key}: expected 1 occurrence, found {counts[key]}")
            elif values.get(key) != expected:
                errors.append(f"{key}: expected {expected!r}, found {values.get(key)!r}")
        if errors:
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"errors": errors, "counts": counts, "values": values},
            )
        return Ok(values)


__all__ = ["PROPERTIES", "SystemPatch", "SystemPatcher"]
