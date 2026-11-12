"""High-level orchestration for the guided v1 unlock.

The session is the only place that combines SP Flash validation, TWRP/ADB and
the FSM. It never automates SP Flash Tool GUI, and it never writes boot or
recovery: those final writes remain TWRP GUI actions confirmed by the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from ..utils.filesystem import ensure_dir
from ..utils.operation_journal import OperationJournal
from .models import UnlockArtifact, UnlockPhase, UnlockProfile
from .session_types import SessionPatchResult, SessionPushResult
from .spflash import SpFlashGuide
from .twrp import TwrpAdb
from .workflow import UnlockWorkflow


@dataclass
class GuidedUnlockSession:
    profile: UnlockProfile
    work_dir: Path
    twrp: TwrpAdb
    guide: SpFlashGuide = field(init=False)
    workflow: UnlockWorkflow = field(init=False)
    boot_backup: UnlockArtifact | None = None
    twrp_image: UnlockArtifact | None = None

    def __post_init__(self) -> None:
        self.work_dir = ensure_dir(Path(self.work_dir).expanduser())
        self.guide = SpFlashGuide(self.profile)
        journal = OperationJournal(self.work_dir / "journal.jsonl")
        self.workflow = UnlockWorkflow(
            self.profile, work_dir=self.work_dir, journal=journal
        )

    @property
    def phase(self) -> UnlockPhase:
        return self.workflow.phase

    def accept_consent(self) -> Result[UnlockPhase]:
        return self.workflow.accept_consent()

    def validate_scatter(self, path: Path | str, *, expected_sha256: str | None = None):
        return self.guide.validate_scatter(path, expected_sha256=expected_sha256)

    def validate_boot_backup(self, path: Path | str) -> Result[UnlockArtifact]:
        result = self.guide.validate_boot_backup(path)
        if isinstance(result, Err):
            return result
        transition = self.workflow.record_boot_backup(result.value)
        if isinstance(transition, Err):
            return transition
        self.boot_backup = result.value
        self.workflow.save_report(self.work_dir)
        return Ok(result.value)

    def validate_twrp_image(self, path: Path | str, *, expected_sha256: str | None = None) -> Result[UnlockArtifact]:
        result = self.guide.validate_twrp(path, expected_sha256=expected_sha256)
        if isinstance(result, Ok):
            self.twrp_image = result.value
            self.workflow.report.add_artifact(result.value)
        return result

    def record_twrp_boot_flash(self) -> Result[UnlockPhase]:
        return self.workflow.record_twrp_boot_flash()

    async def wait_for_twrp(self, timeout_seconds: float = 120.0) -> Result[str]:
        result = await self.twrp.wait_for_twrp(timeout_seconds)
        if isinstance(result, Err):
            return result
        transition = self.workflow.record_twrp_ready(result.value)
        if isinstance(transition, Err):
            return transition
        return Ok(result.value)

    async def patch_system(self) -> Result[SessionPatchResult]:
        mount = await self.twrp.mount_system_rw()
        if isinstance(mount, Err):
            return mount
        self.workflow.record_system_mounted_rw(mount.value.method)

        build_backup = self.work_dir / "build.prop.bak"
        recovery_backup = self.work_dir / "recovery-from-boot.p.bak"
        build = await self.twrp.backup_file("/system/build.prop", build_backup, required=True)
        if isinstance(build, Err):
            return build
        recovery = await self.twrp.backup_file(
            "/system/recovery-from-boot.p", recovery_backup, required=False
        )
        if isinstance(recovery, Err):
            return recovery
        backed_up = self.workflow.record_system_files_backed_up(
            build_backup,
            recovery_from_boot_backup=recovery_backup if isinstance(recovery, Ok) and recovery.value else None,
        )
        if isinstance(backed_up, Err):
            return backed_up

        patched = await self.twrp.patch_build_prop(
            local_backup=build_backup,
            local_patched=self.work_dir / "build.prop.patched",
        )
        if isinstance(patched, Err):
            return patched
        verified = await self.twrp.verify_properties()
        if isinstance(verified, Err):
            return verified
        removed = await self.twrp.remove_recovery_from_boot(recovery_backup)
        if isinstance(removed, Err):
            return removed
        recorded = self.workflow.record_system_patched(patched.value.patch)
        if isinstance(recorded, Err):
            return recorded
        self.workflow.save_report(self.work_dir)
        return Ok(
            SessionPatchResult(
                patch=patched.value,
                verified_properties=verified.value,
                recovery_from_boot_removed=removed.value,
            )
        )

    async def push_final_images(self) -> Result[SessionPushResult]:
        if self.boot_backup is None:
            return Err(
                ErrorCode.ERR_PRECONDITION_NOT_MET,
                details={"reason": "boot backup has not been validated"},
            )
        if self.twrp_image is None:
            return Err(
                ErrorCode.ERR_PRECONDITION_NOT_MET,
                details={"reason": "TWRP image has not been validated"},
            )
        result = await self.twrp.push_final_images(
            self.boot_backup.path, self.twrp_image.path
        )
        if isinstance(result, Err):
            return result
        self.workflow.save_report(self.work_dir)
        return Ok(
            SessionPushResult(
                boot_remote=result.value["boot"],
                recovery_remote=result.value["recovery"],
            )
        )

    def record_final_flashes(self, *, boot: bool, recovery: bool) -> Result[UnlockPhase]:
        return self.workflow.record_final_flashes_confirmed(boot=boot, recovery=recovery)

    def record_rebooted_on_mcc(self, *, mcc_started: bool) -> Result[UnlockPhase]:
        return self.workflow.record_rebooted_on_mcc(mcc_started=mcc_started)

    def record_adb_verified(self, version: str) -> Result[UnlockPhase]:
        return self.workflow.record_adb_verified(version)

    def record_persistence(self, cold_boots: int = 2) -> Result[UnlockPhase]:
        return self.workflow.record_persistence_verified(cold_boots)

    def complete(self) -> Result[Path]:
        transition = self.workflow.complete()
        if isinstance(transition, Err):
            return transition
        saved = self.workflow.save_report(self.work_dir)
        if isinstance(saved, Err):
            return saved
        return Ok(saved.value)

    def fail(self, reason: str) -> Result[UnlockPhase]:
        return self.workflow.fail(reason)

    def mark_indeterminate(self, reason: str) -> Result[UnlockPhase]:
        return self.workflow.mark_indeterminate(reason)

    def rollback(self, *, ok: bool) -> Result[UnlockPhase]:
        return self.workflow.rollback(ok=ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "phase": self.phase.value,
            "status": self.workflow.report.status,
            "work_dir": str(self.work_dir),
            "boot_backup": self.boot_backup.to_dict() if self.boot_backup else None,
            "twrp_image": self.twrp_image.to_dict() if self.twrp_image else None,
            "report": self.workflow.report.to_dict(),
        }


__all__ = ["GuidedUnlockSession"]
