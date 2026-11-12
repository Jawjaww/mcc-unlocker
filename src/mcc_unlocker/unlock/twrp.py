"""TWRP/ADB adapter for the system patch and the final guided steps.

Only fixed, validated paths are used. Every shell command is in a small
whitelist; no arbitrary user command is accepted. The final raw image flashes
are intentionally not automated: TWRP GUI is the reference path.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import shlex
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from .system_patcher import SystemPatch, SystemPatcher

_CONTEXT_RE = re.compile(r"(u:object_r:[^\s]+:s0)")


@dataclass(frozen=True, slots=True)
class TwrpMountResult:
    method: str
    writable: bool


@dataclass(frozen=True, slots=True)
class StorageCheck:
    path: str
    free_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class BackupFile:
    remote: str
    local: Path
    size_bytes: int
    sha256: str
    present: bool = True


@dataclass(frozen=True, slots=True)
class SystemPatchResult:
    patch: SystemPatch
    remote_sha256: str
    local_backup: Path
    context: str | None = None


class TwrpTransport(Protocol):
    async def shell(self, serial: str, command: str) -> Result[str]: ...

    async def push(self, serial: str, local_path: Path | str, remote_path: str) -> Result[str]: ...

    async def pull(self, serial: str, remote_path: str, local_path: Path | str) -> Result[str]: ...


@dataclass
class AdbTwrpTransport:
    adapter: object
    serial: str

    async def shell(self, serial: str, command: str) -> Result[str]:
        return await self.adapter.shell(serial, command)  # type: ignore[attr-defined]

    async def push(self, serial: str, local_path: Path | str, remote_path: str) -> Result[str]:
        return await self.adapter.push(serial, local_path, remote_path)  # type: ignore[attr-defined]

    async def pull(self, serial: str, remote_path: str, local_path: Path | str) -> Result[str]:
        return await self.adapter.pull(serial, remote_path, local_path)  # type: ignore[attr-defined]


@dataclass
class TwrpAdb:
    transport: TwrpTransport
    serial: str
    remote_root: str = "/sdcard"
    sleep: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    poll_interval: float = 2.0

    # ---------------------------------------------------------------- basics
    async def _shell_ok(self, command: str) -> bool:
        result = await self.transport.shell(self.serial, command)
        return isinstance(result, Ok)

    async def wait_for_twrp(
        self, timeout_seconds: float = 120.0, *, poll_interval: float | None = None
    ) -> Result[str]:
        delay = poll_interval or self.poll_interval
        elapsed = 0.0
        last_error: Err | None = None
        while elapsed <= timeout_seconds:
            version = await self.transport.shell(self.serial, "getprop ro.twrp.version")
            if isinstance(version, Ok):
                value = version.value.strip()
                if value:
                    return Ok(value)
                # Some TWRP builds expose the binary even when the property is empty.
                present = await self.transport.shell(self.serial, "which twrp")
                if isinstance(present, Ok) and present.value.strip():
                    return Ok("twrp-present")
            else:
                last_error = version
            await self.sleep(delay)
            elapsed += delay
        details: dict[str, object] = {"timeout_seconds": timeout_seconds}
        if last_error is not None:
            details["last_error"] = last_error.to_dict()
        return Err(ErrorCode.ERR_UNLOCK_TWRP_UNAVAILABLE, details=details)

    async def read_file(self, remote_path: str) -> Result[str]:
        if not remote_path.startswith("/"):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "remote path must be absolute"},
            )
        return await self.transport.shell(self.serial, f"cat {shlex.quote(remote_path)}")

    async def _test_file(self, remote_path: str) -> bool:
        result = await self.transport.shell(
            self.serial, f"test -f {shlex.quote(remote_path)} && echo yes || echo no"
        )
        return isinstance(result, Ok) and "yes" in result.value

    async def _test_dir(self, remote_path: str) -> bool:
        result = await self.transport.shell(
            self.serial, f"test -d {shlex.quote(remote_path)} && echo yes || echo no"
        )
        return isinstance(result, Ok) and "yes" in result.value

    # -------------------------------------------------------------- storage
    async def check_storage(self) -> Result[StorageCheck]:
        if not await self._test_dir(self.remote_root):
            return Err(
                ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
                details={"path": self.remote_root, "reason": "directory missing"},
            )
        token = uuid.uuid4().hex
        local = Path(tempfile.gettempdir()) / f"mcc-storage-{token}.txt"
        remote = f"{self.remote_root.rstrip('/')}/.mcc-storage-{token}.txt"
        try:
            local.write_text("mcc-storage-ok\n", encoding="utf-8")
            pushed = await self.transport.push(self.serial, local, remote)
            if isinstance(pushed, Err):
                return Err(
                    ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
                    details={"path": self.remote_root, "reason": "push failed", "error": pushed.to_dict()},
                )
            read_back = await self.transport.shell(self.serial, f"cat {shlex.quote(remote)}")
            if not isinstance(read_back, Ok) or "mcc-storage-ok" not in read_back.value:
                return Err(
                    ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
                    details={"path": self.remote_root, "reason": "read-back failed"},
                )
            return Ok(StorageCheck(path=self.remote_root))
        finally:
            local.unlink(missing_ok=True)
            await self.transport.shell(self.serial, f"rm -f {shlex.quote(remote)}")

    # --------------------------------------------------------------- mount
    async def _write_test(self) -> bool:
        token = uuid.uuid4().hex
        test_path = f"/system/.mcc-write-{token}"
        written = await self.transport.shell(
            self.serial, f"echo mcc-rw > {shlex.quote(test_path)}"
        )
        if isinstance(written, Err):
            return False
        read_back = await self.transport.shell(
            self.serial, f"cat {shlex.quote(test_path)}"
        )
        cleaned = await self.transport.shell(
            self.serial, f"rm -f {shlex.quote(test_path)}"
        )
        return (
            isinstance(read_back, Ok)
            and "mcc-rw" in read_back.value
            and isinstance(cleaned, Ok)
        )

    async def mount_system_rw(self) -> Result[TwrpMountResult]:
        await self.transport.shell(self.serial, "mount /system")
        remount = await self.transport.shell(self.serial, "remountrw")
        method = "remountrw"
        if isinstance(remount, Err):
            fallback = await self.transport.shell(
                self.serial, "mount -o rw,remount /system"
            )
            if isinstance(fallback, Err):
                return Err(
                    ErrorCode.ERR_UNLOCK_SYSTEM_MOUNT_FAILED,
                    details={
                        "remountrw": remount.to_dict(),
                        "fallback": fallback.to_dict(),
                    },
                )
            method = "mount -o rw,remount /system"

        if await self._write_test():
            return Ok(TwrpMountResult(method=method, writable=True))

        # remountrw can report success while the partition stayed read-only.
        # Try the explicit remount once before refusing to touch build.prop.
        if method == "remountrw":
            fallback = await self.transport.shell(
                self.serial, "mount -o rw,remount /system"
            )
            if isinstance(fallback, Ok) and await self._write_test():
                return Ok(
                    TwrpMountResult(method="mount -o rw,remount /system", writable=True)
                )
        return Err(
            ErrorCode.ERR_UNLOCK_SYSTEM_MOUNT_FAILED,
            details={"method": method, "reason": "write test failed"},
        )

    # ---------------------------------------------------------- file backup
    async def backup_file(self, remote_path: str, local_path: Path, *, required: bool = True) -> Result[BackupFile | None]:
        if not await self._test_file(remote_path):
            if required:
                return Err(
                    ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                    details={"path": remote_path, "reason": "required file missing"},
                )
            return Ok(None)
        destination = Path(local_path)
        pulled = await self.transport.pull(self.serial, remote_path, destination)
        if isinstance(pulled, Err):
            return pulled
        data = destination.read_bytes()
        return Ok(
            BackupFile(
                remote=remote_path,
                local=destination,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )

    async def patch_build_prop(
        self,
        *,
        local_backup: Path,
        local_patched: Path,
        expected_context: str | None = None,
    ) -> Result[SystemPatchResult]:
        if expected_context is None:
            detected = await self.context_of("/system/build.prop")
            if isinstance(detected, Ok):
                expected_context = detected.value
        original = await self.read_file("/system/build.prop")
        if isinstance(original, Err):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "cannot read build.prop", "error": original.to_dict()},
            )
        try:
            original_bytes = original.value.encode("utf-8")
        except UnicodeEncodeError as exc:
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "build.prop encoding", "error": str(exc)},
            )
        patched = SystemPatcher().patch(original_bytes)
        if isinstance(patched, Err):
            return patched
        local_backup.parent.mkdir(parents=True, exist_ok=True)
        local_backup.write_bytes(original_bytes)
        local_patched.write_bytes(patched.value.patched)

        remote_stage = f"{self.remote_root.rstrip('/')}/.mcc-build.prop.tmp"
        remote_target = "/system/build.prop.mcc.tmp"
        pushed = await self.transport.push(self.serial, local_patched, remote_stage)
        if isinstance(pushed, Err):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "push failed", "error": pushed.to_dict()},
            )
        commands = [
            f"cp {shlex.quote(remote_stage)} {shlex.quote(remote_target)}",
            f"chmod 644 {shlex.quote(remote_target)}",
            f"chown 0:0 {shlex.quote(remote_target)}",
        ]
        if expected_context:
            commands.append(
                f"chcon {shlex.quote(expected_context)} {shlex.quote(remote_target)}"
            )
        commands.append(f"mv {shlex.quote(remote_target)} /system/build.prop")
        commands.append("sync")
        for command in commands:
            result = await self.transport.shell(self.serial, command)
            if isinstance(result, Err):
                await self.transport.shell(self.serial, f"rm -f {shlex.quote(remote_target)}")
                await self.transport.shell(self.serial, f"rm -f {shlex.quote(remote_stage)}")
                return Err(
                    ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                    details={"reason": "atomic replace failed", "command": command, "error": result.to_dict()},
                )
        await self.transport.shell(self.serial, f"rm -f {shlex.quote(remote_stage)}")

        verify = await self.read_file("/system/build.prop")
        if isinstance(verify, Err):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "cannot re-read build.prop", "error": verify.to_dict()},
            )
        remote_sha = hashlib.sha256(verify.value.encode("utf-8")).hexdigest()
        if remote_sha != patched.value.patched_sha256:
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={
                    "reason": "re-read hash mismatch",
                    "expected_sha256": patched.value.patched_sha256,
                    "actual_sha256": remote_sha,
                },
            )
        return Ok(
            SystemPatchResult(
                patch=patched.value,
                remote_sha256=remote_sha,
                local_backup=local_backup,
                context=expected_context,
            )
        )

    async def verify_properties(self) -> Result[dict[str, str]]:
        content = await self.read_file("/system/build.prop")
        if isinstance(content, Err):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "cannot read patched build.prop"},
            )
        return SystemPatcher().verify(content.value.encode("utf-8"))

    async def remove_recovery_from_boot(self, local_backup: Path) -> Result[bool]:
        remote = "/system/recovery-from-boot.p"
        if not await self._test_file(remote):
            return Ok(False)
        backup = await self.backup_file(remote, local_backup, required=True)
        if isinstance(backup, Err):
            return backup
        removed = await self.transport.shell(self.serial, f"rm -f {shlex.quote(remote)}")
        if isinstance(removed, Err):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "remove failed", "error": removed.to_dict()},
            )
        if await self._test_file(remote):
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "recovery-from-boot.p still present"},
            )
        return Ok(True)

    async def context_of(self, remote_path: str) -> Result[str | None]:
        result = await self.transport.shell(
            self.serial, f"ls -Z {shlex.quote(remote_path)}"
        )
        if isinstance(result, Err):
            return Ok(None)
        match = _CONTEXT_RE.search(result.value)
        return Ok(match.group(1) if match else None)

    # ------------------------------------------------------------ final push
    async def push_final_images(self, boot_local: Path, recovery_local: Path) -> Result[dict[str, str]]:
        storage = await self.check_storage()
        if isinstance(storage, Err):
            return storage
        boot_remote = f"{self.remote_root.rstrip('/')}/bootimg.bin"
        recovery_remote = f"{self.remote_root.rstrip('/')}/recovery.bin"
        for local, remote in ((boot_local, boot_remote), (recovery_local, recovery_remote)):
            pushed = await self.transport.push(self.serial, local, remote)
            if isinstance(pushed, Err):
                return Err(
                    ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
                    details={"reason": "final image push failed", "remote": remote, "error": pushed.to_dict()},
                )
            if not await self._test_file(remote):
                return Err(
                    ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
                    details={"reason": "pushed image not visible", "remote": remote},
                )
        return Ok({"boot": boot_remote, "recovery": recovery_remote})

    async def reboot(self) -> Result[str]:
        result = await self.transport.shell(self.serial, "reboot")
        if isinstance(result, Err):
            return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"reason": "reboot failed"})
        return Ok("reboot requested")

    async def power_off(self) -> Result[str]:
        result = await self.transport.shell(self.serial, "twrp reboot poweroff")
        if isinstance(result, Err):
            fallback = await self.transport.shell(self.serial, "reboot -p")
            if isinstance(fallback, Err):
                return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"reason": "poweroff failed"})
        return Ok("poweroff requested")


__all__ = [
    "AdbTwrpTransport",
    "BackupFile",
    "StorageCheck",
    "SystemPatchResult",
    "TwrpAdb",
    "TwrpMountResult",
    "TwrpTransport",
]
