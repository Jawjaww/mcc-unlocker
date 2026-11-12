"""TWRP/ADB adapter tests with a command-level fake (no robot)."""

from __future__ import annotations

import asyncio
import hashlib
import shlex
from pathlib import Path

from mcc_unlocker.core.errors import ErrorCode
from mcc_unlocker.core.result import Err, Ok
from mcc_unlocker.unlock.twrp import TwrpAdb


class FakeTwrpTransport:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {
            "/system/build.prop": b"ro.foo=bar\npersist.service.adb.enable=0\n",
            "/system/recovery-from-boot.p": b"RECOVERY-CHECK",
        }
        self.commands: list[str] = []
        self.remountrw_ok = True
        self.writable = True
        self.twrp_version = "3.7.0_9-0"

    async def shell(self, serial: str, command: str):
        self.commands.append(command)
        if command == "getprop ro.twrp.version":
            return Ok(self.twrp_version)
        if command == "which twrp":
            return Ok("/sbin/twrp\n")
        if command.startswith("test -d "):
            path = shlex.split(command)[2]
            return Ok("yes\n" if path in {"/sdcard", "/data/media/0"} else "no\n")
        if command.startswith("test -f "):
            path = shlex.split(command)[2]
            return Ok("yes\n" if path in self.files else "no\n")
        if command.startswith("cat "):
            path = shlex.split(command)[1]
            data = self.files.get(path)
            return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"path": path}) if data is None else Ok(data.decode("latin-1"))
        if command.startswith("echo mcc-rw > "):
            if not self.writable:
                return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"reason": "ro"})
            path = shlex.split(command)[3]
            self.files[path] = b"mcc-rw\n"
            return Ok("")
        if command.startswith("rm -f "):
            path = shlex.split(command)[2]
            self.files.pop(path, None)
            return Ok("")
        if command == "mount /system":
            return Ok("")
        if command == "remountrw":
            return Ok("") if self.remountrw_ok else Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"reason": "no remountrw"})
        if command.startswith("mount -o rw,remount"):
            return Ok("")
        if command.startswith("ls -Z "):
            return Ok("-rw-r--r-- root root u:object_r:system_file:s0 /system/build.prop\n")
        if command.startswith("cp "):
            parts = shlex.split(command)
            self.files[parts[2]] = self.files[parts[1]]
            return Ok("")
        if command.startswith("chmod ") or command.startswith("chown ") or command.startswith("chcon "):
            return Ok("")
        if command.startswith("mv "):
            parts = shlex.split(command)
            self.files[parts[2]] = self.files.pop(parts[1])
            return Ok("")
        if command == "sync":
            return Ok("")
        if command == "reboot":
            return Ok("")
        if command.startswith("twrp reboot"):
            return Ok("")
        return Ok("")

    async def push(self, serial: str, local_path: Path | str, remote_path: str):
        self.commands.append(f"push {local_path} {remote_path}")
        self.files[remote_path] = Path(local_path).read_bytes()
        return Ok("")

    async def pull(self, serial: str, remote_path: str, local_path: Path | str):
        self.commands.append(f"pull {remote_path} {local_path}")
        data = self.files.get(remote_path)
        if data is None:
            return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"remote": remote_path})
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(data)
        return Ok("")


async def _no_sleep(_: float) -> None:
    return None


def _twrp(fake: FakeTwrpTransport) -> TwrpAdb:
    return TwrpAdb(fake, "serial", sleep=_no_sleep, poll_interval=0)


def test_wait_for_twrp_and_storage(tmp_path):
    fake = FakeTwrpTransport()
    twrp = _twrp(fake)
    assert asyncio.run(twrp.wait_for_twrp(timeout_seconds=1)).value.startswith("3.7")
    storage = asyncio.run(twrp.check_storage())
    assert storage.is_ok
    assert "/sdcard" in storage.value.path


def test_mount_system_uses_remountrw(tmp_path):
    fake = FakeTwrpTransport()
    result = asyncio.run(_twrp(fake).mount_system_rw())
    assert result.is_ok
    assert result.value.method == "remountrw"
    assert any(command == "remountrw" for command in fake.commands)


def test_mount_system_falls_back_to_explicit_remount(tmp_path):
    fake = FakeTwrpTransport()
    fake.remountrw_ok = False
    result = asyncio.run(_twrp(fake).mount_system_rw())
    assert result.is_ok
    assert result.value.method == "mount -o rw,remount /system"


def test_mount_system_refuses_if_write_test_fails(tmp_path):
    fake = FakeTwrpTransport()
    fake.writable = False
    result = asyncio.run(_twrp(fake).mount_system_rw())
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_SYSTEM_MOUNT_FAILED


def test_patch_build_prop_and_remove_recovery_check(tmp_path):
    fake = FakeTwrpTransport()
    twrp = _twrp(fake)
    context = asyncio.run(twrp.context_of("/system/build.prop"))
    assert context.is_ok and context.value == "u:object_r:system_file:s0"
    backup = tmp_path / "build.prop.bak"
    patched = tmp_path / "build.prop.patched"
    result = asyncio.run(
        twrp.patch_build_prop(
            local_backup=backup,
            local_patched=patched,
            expected_context=context.value,
        )
    )
    assert result.is_ok, result
    assert b"persist.service.adb.enable=1" in fake.files["/system/build.prop"]
    assert backup.read_bytes().startswith(b"ro.foo=bar")
    assert hashlib.sha256(fake.files["/system/build.prop"]).hexdigest() == result.value.remote_sha256
    verified = asyncio.run(twrp.verify_properties())
    assert verified.is_ok
    removed = asyncio.run(twrp.remove_recovery_from_boot(tmp_path / "recovery-from-boot.p.bak"))
    assert removed.is_ok and removed.value is True
    assert "/system/recovery-from-boot.p" not in fake.files


def test_patch_hash_mismatch_is_failed(tmp_path):
    fake = FakeTwrpTransport()
    twrp = _twrp(fake)
    # Make the shell return a different content after the mv.
    original_shell = fake.shell

    async def tampered(serial, command):
        if command == "cat /system/build.prop":
            return Ok("tampered\n")
        return await original_shell(serial, command)

    fake.shell = tampered  # type: ignore[method-assign]
    result = asyncio.run(
        twrp.patch_build_prop(
            local_backup=tmp_path / "b",
            local_patched=tmp_path / "p",
        )
    )
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED


def test_final_images_are_pushed_to_reference_names(tmp_path):
    fake = FakeTwrpTransport()
    boot = tmp_path / "boot_backup.img"
    recovery = tmp_path / "twrp_recovery.img"
    boot.write_bytes(b"boot")
    recovery.write_bytes(b"twrp")
    result = asyncio.run(_twrp(fake).push_final_images(boot, recovery))
    assert result.is_ok
    assert result.value == {
        "boot": "/sdcard/bootimg.bin",
        "recovery": "/sdcard/recovery.bin",
    }
    assert fake.files["/sdcard/bootimg.bin"] == b"boot"
    assert fake.files["/sdcard/recovery.bin"] == b"twrp"
