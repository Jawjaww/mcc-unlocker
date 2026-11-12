"""Guided unlock FSM and report tests."""

from __future__ import annotations

import hashlib

from mcc_unlocker.core.errors import ErrorCode
from mcc_unlocker.core.result import Err
from mcc_unlocker.unlock.models import ArtifactKind, UnlockArtifact, UnlockPhase, UnlockProfile
from mcc_unlocker.unlock.system_patcher import SystemPatcher
from mcc_unlocker.unlock.workflow import UnlockWorkflow


def _boot_artifact(tmp_path):
    path = tmp_path / "boot_backup.img"
    path.write_bytes(b"\0" * 0x1000000)
    return UnlockArtifact(
        kind=ArtifactKind.BOOT_BACKUP,
        path=path,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_workflow_refuses_boot_backup_before_consent(tmp_path):
    workflow = UnlockWorkflow(UnlockProfile.reference(), work_dir=tmp_path)
    result = workflow.record_boot_backup(_boot_artifact(tmp_path))
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_STEP_OUT_OF_ORDER


def test_workflow_happy_path_and_report(tmp_path):
    workflow = UnlockWorkflow(UnlockProfile.reference(), work_dir=tmp_path)
    assert workflow.accept_consent().is_ok
    assert workflow.record_boot_backup(_boot_artifact(tmp_path)).is_ok
    assert workflow.record_twrp_boot_flash().is_ok
    assert workflow.record_twrp_ready("3.7.0").is_ok
    assert workflow.record_system_mounted_rw("remountrw").is_ok
    backup = tmp_path / "build.prop.bak"
    backup.write_text("ro.foo=bar\n")
    assert workflow.record_system_files_backed_up(backup).is_ok
    patch = SystemPatcher().patch(b"ro.foo=bar\n")
    assert workflow.record_system_patched(patch.value).is_ok
    assert workflow.record_final_flashes_confirmed(boot=True, recovery=True).is_ok
    assert workflow.record_rebooted_on_mcc(mcc_started=True).is_ok
    assert workflow.record_adb_verified("Android Debug Bridge version 1.0.41").is_ok
    assert workflow.record_persistence_verified(2).is_ok
    assert workflow.complete().is_ok
    assert workflow.phase is UnlockPhase.COMPLETED
    report = workflow.save_report()
    assert report.is_ok
    assert (tmp_path / "unlock_report.json").is_file()
    text = (tmp_path / "unlock_report.md").read_text()
    assert "COMPLETED" in text
    assert "preuve bit-à-bit" in text.lower()


def test_cannot_complete_early_or_skip_persistence(tmp_path):
    workflow = UnlockWorkflow(UnlockProfile.reference(), work_dir=tmp_path)
    assert isinstance(workflow.complete(), Err)
    workflow.accept_consent()
    workflow.record_boot_backup(_boot_artifact(tmp_path))
    assert isinstance(workflow.record_persistence_verified(2), Err)


def test_failure_and_rollback_are_terminal(tmp_path):
    workflow = UnlockWorkflow(UnlockProfile.reference(), work_dir=tmp_path)
    assert workflow.fail("test").is_ok
    assert workflow.phase is UnlockPhase.FAILED
    assert isinstance(workflow.accept_consent(), Err)


def test_persistence_requires_two_cold_boots(tmp_path):
    workflow = UnlockWorkflow(UnlockProfile.reference(), work_dir=tmp_path)
    workflow.accept_consent()
    workflow.record_boot_backup(_boot_artifact(tmp_path))
    workflow.record_twrp_boot_flash()
    workflow.record_twrp_ready("3.7")
    workflow.record_system_mounted_rw("remountrw")
    backup = tmp_path / "build.prop.bak"
    backup.write_text("x")
    workflow.record_system_files_backed_up(backup)
    workflow.record_system_patched(SystemPatcher().patch(b"x").value)
    workflow.record_final_flashes_confirmed(boot=True, recovery=True)
    workflow.record_rebooted_on_mcc(mcc_started=True)
    workflow.record_adb_verified("1.0")
    result = workflow.record_persistence_verified(1)
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_PRECONDITION_NOT_MET
