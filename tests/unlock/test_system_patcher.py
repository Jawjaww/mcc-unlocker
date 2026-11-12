"""Pure build.prop patcher tests."""

from __future__ import annotations

from mcc_unlocker.core.errors import ErrorCode
from mcc_unlocker.core.result import Err
from mcc_unlocker.unlock.system_patcher import PROPERTIES, SystemPatcher


def test_patch_replaces_duplicates_and_preserves_comments():
    original = b"""# MCC build.prop
ro.foo=bar
persist.service.adb.enable=0
persist.service.adb.enable=1
persist.sys.usb.config=mtp, adb
qemu.hw.mainkeys=1
"""
    result = SystemPatcher().patch(original)
    assert result.is_ok
    patched = result.value.patched.decode()
    assert "# MCC build.prop" in patched
    assert "ro.foo=bar" in patched
    assert patched.count("persist.service.adb.enable=") == 1
    assert patched.count("persist.sys.usb.config=") == 1
    assert "persist.sys.usb.config=mtp,adb" in patched
    assert "qemu.hw.mainkeys=0" in patched
    assert "persist.service.debuggable=1" in patched
    assert SystemPatcher().verify(result.value.patched).is_ok


def test_patch_is_idempotent():
    original = b"ro.foo=bar\n"
    first = SystemPatcher().patch(original)
    second = SystemPatcher().patch(first.value.patched)
    assert first.value.patched == second.value.patched
    assert first.value.patched_sha256 == second.value.patched_sha256


def test_verify_rejects_missing_or_duplicate_properties():
    missing = b"ro.foo=bar\n"
    assert isinstance(SystemPatcher().verify(missing), Err)
    duplicate = b"\n".join(
        f"{key}={value}".encode() for key, value in PROPERTIES
    ) + b"\npersist.service.adb.enable=1\n"
    result = SystemPatcher().verify(duplicate)
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED


def test_non_utf8_is_refused():
    result = SystemPatcher().patch(b"\xff\xfe")
    assert isinstance(result, Err)
