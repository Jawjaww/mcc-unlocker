"""End-to-end simulation of the guided unlock session (no robot)."""

from __future__ import annotations

import asyncio

from mcc_unlocker.unlock.models import UnlockPhase, UnlockProfile
from mcc_unlocker.unlock.session import GuidedUnlockSession
from mcc_unlocker.unlock.twrp import TwrpAdb
from tests.unlock.test_twrp import FakeTwrpTransport, _no_sleep


def _session(tmp_path):
    fake = FakeTwrpTransport()
    twrp = TwrpAdb(fake, "serial", sleep=_no_sleep, poll_interval=0)
    session = GuidedUnlockSession(
        UnlockProfile.reference(),
        tmp_path / "session",
        twrp,
    )
    return fake, session


def test_session_happy_path_simulated(tmp_path):
    fake, session = _session(tmp_path)
    boot = tmp_path / "boot_backup.img"
    boot.write_bytes(b"\0" * UnlockProfile.reference().boot_size)
    twrp_img = tmp_path / "twrp_recovery.img"
    twrp_img.write_bytes(b"TWRP-IMAGE")

    assert session.accept_consent().is_ok
    assert session.validate_boot_backup(boot).is_ok
    assert session.validate_twrp_image(twrp_img).is_ok
    assert session.record_twrp_boot_flash().is_ok
    assert asyncio.run(session.wait_for_twrp(1)).is_ok
    patch = asyncio.run(session.patch_system())
    assert patch.is_ok, patch
    assert patch.value.recovery_from_boot_removed is True
    assert session.phase is UnlockPhase.SYSTEM_PATCHED
    pushed = asyncio.run(session.push_final_images())
    assert pushed.is_ok, pushed
    assert fake.files["/sdcard/bootimg.bin"] == boot.read_bytes()
    assert session.record_final_flashes(boot=True, recovery=True).is_ok
    assert session.record_rebooted_on_mcc(mcc_started=True).is_ok
    assert session.record_adb_verified("adb 1.0.41").is_ok
    assert session.record_persistence(2).is_ok
    completed = session.complete()
    assert completed.is_ok, completed
    assert session.phase is UnlockPhase.COMPLETED
    report = (tmp_path / "session" / "unlock_report.md").read_text()
    assert "COMPLETED" in report
    assert "boot_backup" in report


def test_session_refuses_final_push_without_backup(tmp_path):
    _, session = _session(tmp_path)
    session.accept_consent()
    result = asyncio.run(session.push_final_images())
    assert not result.is_ok
    assert result.code.value == "ERR_PRECONDITION_NOT_MET"


def test_session_marks_indeterminate(tmp_path):
    _, session = _session(tmp_path)
    session.accept_consent()
    assert session.mark_indeterminate("cable unplugged").is_ok
    assert session.phase is UnlockPhase.INDETERMINATE
    assert session.workflow.report.status == "INDETERMINATE"
