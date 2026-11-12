"""Short, deterministic FSM for the guided v1 unlock.

The FSM does no I/O by itself. It records evidence produced by SP Flash Tool,
TWRP/ADB and the user, and refuses transitions that would let the UI declare
success without the required steps.
"""

from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from ..utils.filesystem import atomic_write_json, atomic_write_text, ensure_dir
from ..utils.hashing import sha256_file
from ..utils.operation_journal import OperationJournal
from .models import ArtifactKind, UnlockArtifact, UnlockPhase, UnlockProfile, UnlockReport
from .system_patcher import SystemPatch


class UnlockEvent(str, Enum):
    CONSENT = "CONSENT"
    BOOT_BACKUP_VERIFIED = "BOOT_BACKUP_VERIFIED"
    TWRP_BOOT_FLASHED = "TWRP_BOOT_FLASHED"
    TWRP_READY = "TWRP_READY"
    SYSTEM_MOUNTED_RW = "SYSTEM_MOUNTED_RW"
    SYSTEM_FILES_BACKED_UP = "SYSTEM_FILES_BACKED_UP"
    SYSTEM_PATCHED = "SYSTEM_PATCHED"
    FINAL_FLASHES_CONFIRMED = "FINAL_FLASHES_CONFIRMED"
    REBOOTED_ON_MCC = "REBOOTED_ON_MCC"
    ADB_VERIFIED = "ADB_VERIFIED"
    PERSISTENCE_VERIFIED = "PERSISTENCE_VERIFIED"
    COMPLETE = "COMPLETE"
    ROLLBACK = "ROLLBACK"
    ROLLBACK_OK = "ROLLBACK_OK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    FAIL = "FAIL"
    CANCEL = "CANCEL"
    INDETERMINATE = "INDETERMINATE"


_TRANSITIONS: Mapping[UnlockPhase, Mapping[UnlockEvent, UnlockPhase]] = {
    UnlockPhase.PREFLIGHT: {UnlockEvent.CONSENT: UnlockPhase.CONSENT},
    UnlockPhase.CONSENT: {UnlockEvent.BOOT_BACKUP_VERIFIED: UnlockPhase.BOOT_BACKUP_VERIFIED},
    UnlockPhase.BOOT_BACKUP_VERIFIED: {
        UnlockEvent.TWRP_BOOT_FLASHED: UnlockPhase.TWRP_BOOT_FLASHED
    },
    UnlockPhase.TWRP_BOOT_FLASHED: {UnlockEvent.TWRP_READY: UnlockPhase.TWRP_READY},
    UnlockPhase.TWRP_READY: {
        UnlockEvent.SYSTEM_MOUNTED_RW: UnlockPhase.SYSTEM_MOUNTED_RW
    },
    UnlockPhase.SYSTEM_MOUNTED_RW: {
        UnlockEvent.SYSTEM_FILES_BACKED_UP: UnlockPhase.SYSTEM_FILES_BACKED_UP
    },
    UnlockPhase.SYSTEM_FILES_BACKED_UP: {
        UnlockEvent.SYSTEM_PATCHED: UnlockPhase.SYSTEM_PATCHED
    },
    UnlockPhase.SYSTEM_PATCHED: {
        UnlockEvent.FINAL_FLASHES_CONFIRMED: UnlockPhase.FINAL_FLASHES_CONFIRMED
    },
    UnlockPhase.FINAL_FLASHES_CONFIRMED: {
        UnlockEvent.REBOOTED_ON_MCC: UnlockPhase.REBOOTED_ON_MCC
    },
    UnlockPhase.REBOOTED_ON_MCC: {UnlockEvent.ADB_VERIFIED: UnlockPhase.ADB_VERIFIED},
    UnlockPhase.ADB_VERIFIED: {
        UnlockEvent.PERSISTENCE_VERIFIED: UnlockPhase.PERSISTENCE_VERIFIED
    },
    UnlockPhase.PERSISTENCE_VERIFIED: {UnlockEvent.COMPLETE: UnlockPhase.COMPLETED},
}

class UnlockWorkflow:
    def __init__(
        self,
        profile: UnlockProfile | None = None,
        *,
        work_dir: Path | str | None = None,
        session_id: str | None = None,
        journal: OperationJournal | None = None,
    ) -> None:
        self.profile = profile or UnlockProfile.reference()
        self.phase = UnlockPhase.PREFLIGHT
        self.session_id = session_id or uuid.uuid4().hex
        self.work_dir = ensure_dir(Path(work_dir).expanduser()) if work_dir else None
        self.report = UnlockReport(session_id=self.session_id, profile=self.profile, phase=self.phase)
        self.journal = journal
        self._operation_id = f"unlock-{self.session_id[:16]}"
        if self.journal is not None:
            started = self.journal.record_start(
                operation_id=self._operation_id,
                operation="guided_unlock",
                target=self.profile.profile_id,
                details={"firmware": self.profile.firmware, "source": self.profile.source},
            )
            if isinstance(started, Err):
                raise ValueError(started.message)

    # ------------------------------------------------------------------ helpers
    def allowed_events(self) -> frozenset[UnlockEvent]:
        if self.phase.is_terminal:
            return frozenset()
        return frozenset(_TRANSITIONS.get(self.phase, {}))

    def _transition(self, event: UnlockEvent, details: Mapping[str, Any] | None = None) -> Result[UnlockPhase]:
        terminal_targets = {
            UnlockEvent.FAIL: UnlockPhase.FAILED,
            UnlockEvent.CANCEL: UnlockPhase.CANCELLED,
            UnlockEvent.INDETERMINATE: UnlockPhase.INDETERMINATE,
            UnlockEvent.ROLLBACK: UnlockPhase.ROLLBACK,
            UnlockEvent.ROLLBACK_FAILED: UnlockPhase.ROLLBACK_FAILED,
        }
        if self.phase.is_terminal:
            return Err(
                ErrorCode.ERR_UNLOCK_STEP_OUT_OF_ORDER,
                details={"phase": self.phase.value, "event": event.value},
            )
        if event in terminal_targets:
            target = terminal_targets[event]
        else:
            target = _TRANSITIONS.get(self.phase, {}).get(event)
        if target is None:
            return Err(
                ErrorCode.ERR_UNLOCK_STEP_OUT_OF_ORDER,
                details={
                    "phase": self.phase.value,
                    "event": event.value,
                    "allowed": sorted(item.value for item in self.allowed_events()),
                },
            )
        previous = self.phase
        self.phase = target
        self.report.phase = target
        if self.journal is not None:
            self.journal.record_phase(
                operation_id=self._operation_id,
                phase=f"{previous.value}->{target.value}",
                details=dict(details or {}),
            )
        return Ok(target)

    def _record_artifact(self, artifact: UnlockArtifact) -> None:
        self.report.add_artifact(artifact)

    def _check_expected_size(self, artifact: UnlockArtifact, expected: int) -> Result[None]:
        if artifact.size_bytes != expected:
            return Err(
                ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
                details={
                    "expected_size": expected,
                    "actual_size": artifact.size_bytes,
                    "path": str(artifact.path),
                },
            )
        return Ok(None)

    # --------------------------------------------------------------- actions
    def accept_consent(self) -> Result[UnlockPhase]:
        return self._transition(UnlockEvent.CONSENT, {"owner_consent": True})

    def record_boot_backup(self, artifact: UnlockArtifact) -> Result[UnlockPhase]:
        if artifact.kind is not ArtifactKind.BOOT_BACKUP:
            return Err(
                ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
                details={"reason": "artifact is not a boot backup"},
            )
        checked = self._check_expected_size(artifact, self.profile.boot_size)
        if isinstance(checked, Err):
            return checked
        transition = self._transition(
            UnlockEvent.BOOT_BACKUP_VERIFIED, {"sha256": artifact.sha256}
        )
        if isinstance(transition, Ok):
            self._record_artifact(artifact)
            self.report.checks["boot_backup_sha256"] = artifact.sha256
            self.report.checks["boot_backup_size"] = artifact.size_bytes
        return transition

    def record_twrp_boot_flash(self) -> Result[UnlockPhase]:
        return self._transition(UnlockEvent.TWRP_BOOT_FLASHED)

    def record_twrp_ready(self, version: str) -> Result[UnlockPhase]:
        if not version.strip():
            return Err(ErrorCode.ERR_UNLOCK_TWRP_UNAVAILABLE, details={"reason": "empty version"})
        transition = self._transition(UnlockEvent.TWRP_READY, {"version": version.strip()})
        if isinstance(transition, Ok):
            self.report.checks["twrp_version"] = version.strip()
        return transition

    def record_system_mounted_rw(self, method: str) -> Result[UnlockPhase]:
        transition = self._transition(UnlockEvent.SYSTEM_MOUNTED_RW, {"method": method})
        if isinstance(transition, Ok):
            self.report.checks["system_mount_method"] = method
        return transition

    def record_system_files_backed_up(
        self,
        build_prop_backup: Path | str,
        *,
        recovery_from_boot_backup: Path | str | None = None,
    ) -> Result[UnlockPhase]:
        build_path = Path(build_prop_backup).expanduser()
        if not build_path.is_file():
            return Err(
                ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
                details={"reason": "build.prop backup missing", "path": str(build_path)},
            )
        recovery_path = (
            Path(recovery_from_boot_backup).expanduser()
            if recovery_from_boot_backup is not None
            else None
        )
        transition = self._transition(UnlockEvent.SYSTEM_FILES_BACKED_UP)
        if isinstance(transition, Err):
            return transition
        self._record_artifact(
            UnlockArtifact(
                kind=ArtifactKind.BUILD_PROP_BACKUP,
                path=build_path,
                size_bytes=build_path.stat().st_size,
                sha256=sha256_file(build_path),
                source="twrp_pull",
            )
        )
        if recovery_path is not None and recovery_path.is_file():
            self._record_artifact(
                UnlockArtifact(
                    kind=ArtifactKind.RECOVERY_FROM_BOOT_BACKUP,
                    path=recovery_path,
                    size_bytes=recovery_path.stat().st_size,
                    sha256=sha256_file(recovery_path),
                    source="twrp_pull",
                )
            )
        self.report.checks["recovery_from_boot_backup_present"] = bool(
            recovery_path is not None and recovery_path.is_file()
        )
        return transition

    def record_system_patched(self, patch: SystemPatch) -> Result[UnlockPhase]:
        transition = self._transition(UnlockEvent.SYSTEM_PATCHED)
        if isinstance(transition, Ok):
            self.report.checks["build_prop_original_sha256"] = patch.original_sha256
            self.report.checks["build_prop_patched_sha256"] = patch.patched_sha256
            self.report.checks["build_prop_properties"] = dict(patch.properties)
        return transition

    def record_final_flashes_confirmed(self, *, boot: bool, recovery: bool) -> Result[UnlockPhase]:
        if not (boot and recovery):
            return Err(
                ErrorCode.ERR_UNLOCK_NOT_CONFIRMED,
                details={"boot_confirmed": boot, "recovery_confirmed": recovery},
            )
        transition = self._transition(UnlockEvent.FINAL_FLASHES_CONFIRMED)
        if isinstance(transition, Ok):
            self.report.checks["final_boot_flash_confirmed"] = True
            self.report.checks["final_recovery_flash_confirmed"] = True
        return transition

    def record_rebooted_on_mcc(self, *, mcc_started: bool) -> Result[UnlockPhase]:
        if not mcc_started:
            return Err(
                ErrorCode.ERR_UNLOCK_NOT_CONFIRMED,
                details={"reason": "MCC did not start"},
            )
        return self._transition(UnlockEvent.REBOOTED_ON_MCC)

    def record_adb_verified(self, version: str) -> Result[UnlockPhase]:
        if not version.strip():
            return Err(ErrorCode.ERR_ADB_NOT_AVAILABLE, details={"reason": "empty adb version"})
        transition = self._transition(UnlockEvent.ADB_VERIFIED)
        if isinstance(transition, Ok):
            self.report.checks["adb_version"] = version.strip()
        return transition

    def record_persistence_verified(self, cold_boots: int) -> Result[UnlockPhase]:
        if cold_boots < 2:
            return Err(
                ErrorCode.ERR_PRECONDITION_NOT_MET,
                details={"cold_boots": cold_boots, "required": 2},
            )
        self.report.checks["cold_boots"] = cold_boots
        return self._transition(UnlockEvent.PERSISTENCE_VERIFIED)

    def complete(self) -> Result[UnlockPhase]:
        result = self._transition(UnlockEvent.COMPLETE)
        if isinstance(result, Ok):
            self.report.status = "COMPLETED"
            self.report.warnings.append(
                "Succès fonctionnel : le déblocage n'inclut pas de preuve bit-à-bit des partitions finales."
            )
            self._finish_journal("succeeded", verification=dict(self.report.checks))
        return result

    def fail(self, reason: str, *, details: Mapping[str, Any] | None = None) -> Result[UnlockPhase]:
        self.report.status = "FAILED"
        self.report.warnings.append(reason)
        result = self._transition(UnlockEvent.FAIL, {"reason": reason, **dict(details or {})})
        self._finish_journal("failed", details={"reason": reason})
        return result

    def cancel(self, reason: str = "cancelled by user") -> Result[UnlockPhase]:
        self.report.status = "CANCELLED"
        result = self._transition(UnlockEvent.CANCEL, {"reason": reason})
        self._finish_journal("cancelled")
        return result

    def mark_indeterminate(self, reason: str) -> Result[UnlockPhase]:
        self.report.status = "INDETERMINATE"
        result = self._transition(UnlockEvent.INDETERMINATE, {"reason": reason})
        self._finish_journal("indeterminate", details={"reason": reason}, indeterminate=True)
        return result

    def rollback(self, *, ok: bool) -> Result[UnlockPhase]:
        if ok:
            self.report.status = "ROLLBACK"
            result = self._transition(UnlockEvent.ROLLBACK, {"ok": True})
            self._finish_journal("cancelled", details={"reason": "rollback"})
            return result
        self.report.status = "ROLLBACK_FAILED"
        result = self._transition(UnlockEvent.ROLLBACK_FAILED)
        self._finish_journal("failed", details={"reason": "rollback failed"})
        return result

    # ------------------------------------------------------------- persistence
    def _finish_journal(
        self,
        status: str,
        *,
        verification: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        indeterminate: bool = False,
    ) -> None:
        if self.journal is None:
            return
        self.journal.record_finish(
            operation_id=self._operation_id,
            status=status,
            verification=verification,
            details=details,
            indeterminate=indeterminate,
        )

    def save_report(self, directory: Path | str | None = None) -> Result[Path]:
        if self.work_dir is None and directory is None:
            return Err(
                ErrorCode.ERR_ENV_STORAGE_PERMISSION,
                details={"reason": "no work directory for report"},
            )
        target_dir = ensure_dir(Path(directory).expanduser() if directory else self.work_dir)
        json_path = target_dir / "unlock_report.json"
        md_path = target_dir / "unlock_report.md"
        try:
            atomic_write_json(json_path, self.report.to_dict())
            atomic_write_text(md_path, self.report.to_markdown())
        except OSError as exc:
            return Err(ErrorCode.ERR_ENV_STORAGE_PERMISSION, details={"error": str(exc)})
        return Ok(json_path)

    @property
    def report_path(self) -> Path | None:
        if self.work_dir is None:
            return None
        return self.work_dir / "unlock_report.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "phase": self.phase.value,
            "status": self.report.status,
            "allowed_events": sorted(event.value for event in self.allowed_events()),
            "profile": self.profile.to_dict(),
            "report": self.report.to_dict(),
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"UnlockWorkflow(phase={self.phase.value}, session={self.session_id[:8]})"


__all__ = ["UnlockEvent", "UnlockWorkflow"]
