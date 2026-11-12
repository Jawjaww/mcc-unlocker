"""Immutable models for the guided v1 unlock path.

The reference procedure is intentionally simple: SP Flash Tool performs the
initial readback and the TWRP-in-boot flash, TWRP/ADB patches ``build.prop``,
then TWRP GUI flashes the original boot and TWRP recovery. This module models
the evidence and the phases; it never claims a bit-for-bit proof unless one was
explicitly performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class UnlockPhase(str, Enum):
    PREFLIGHT = "PREFLIGHT"
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
    COMPLETED = "COMPLETED"
    ROLLBACK = "ROLLBACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INDETERMINATE = "INDETERMINATE"

    @property
    def is_terminal(self) -> bool:
        return self in {
            UnlockPhase.COMPLETED,
            UnlockPhase.ROLLBACK,
            UnlockPhase.ROLLBACK_FAILED,
            UnlockPhase.FAILED,
            UnlockPhase.CANCELLED,
            UnlockPhase.INDETERMINATE,
        }


class ArtifactKind(str, Enum):
    BOOT_BACKUP = "boot_backup"
    RECOVERY_BACKUP = "recovery_backup"
    SYSTEM_BACKUP = "system_backup"
    TWRP_IMAGE = "twrp_image"
    SCATTER = "scatter"
    BUILD_PROP_BACKUP = "build_prop_backup"
    RECOVERY_FROM_BOOT_BACKUP = "recovery_from_boot_backup"
    READBACK_CONTROL = "readback_control"


@dataclass(frozen=True, slots=True)
class ScatterPartition:
    name: str
    start_address: int
    size_bytes: int
    region: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_address": f"0x{self.start_address:x}",
            "size_bytes": self.size_bytes,
            "region": self.region,
        }


@dataclass(frozen=True, slots=True)
class ScatterInfo:
    project: str
    platform: str
    partitions: Mapping[str, ScatterPartition]
    sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "partitions", MappingProxyType(dict(self.partitions)))

    def partition(self, name: str) -> ScatterPartition | None:
        return self.partitions.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "platform": self.platform,
            "sha256": self.sha256,
            "partitions": {name: item.to_dict() for name, item in sorted(self.partitions.items())},
        }


@dataclass(frozen=True, slots=True)
class ReferenceProfile:
    """Declared reference values, never a hardware observation.

    The values come from the community scatter for ``l706_dfbh_v_695``. They
    are only defaults for the reference device and must be confirmed by the
    actual scatter/readback before any write.
    """

    profile_id: str = "l706_dfbh_v_695"
    project: str = "l706_dfbh_v_695"
    platform: str = "MT6580"
    firmware: str = "4921"
    boot_start: int = 0x1D20000
    boot_size: int = 0x1000000
    recovery_start: int = 0x2D20000
    recovery_size: int = 0x1000000
    system_start: int = 0xA800000
    system_size: int = 0x60000000
    sdcard: str = "/sdcard"
    source: str = "declared_reference_scatter"
    confirmed: bool = False

    def to_profile(self) -> "UnlockProfile":
        return UnlockProfile(
            profile_id=self.profile_id,
            project=self.project,
            platform=self.platform,
            firmware=self.firmware,
            boot_start=self.boot_start,
            boot_size=self.boot_size,
            recovery_start=self.recovery_start,
            recovery_size=self.recovery_size,
            system_start=self.system_start,
            system_size=self.system_size,
            sdcard=self.sdcard,
            source=self.source,
            confirmed=self.confirmed,
        )


@dataclass(frozen=True, slots=True)
class UnlockProfile:
    profile_id: str
    project: str
    platform: str
    firmware: str
    boot_start: int
    boot_size: int
    recovery_start: int
    recovery_size: int
    system_start: int
    system_size: int
    sdcard: str = "/sdcard"
    source: str = "declared_reference_scatter"
    confirmed: bool = False
    scatter_sha256: str | None = None

    @classmethod
    def reference(cls) -> "UnlockProfile":
        return ReferenceProfile().to_profile()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "project": self.project,
            "platform": self.platform,
            "firmware": self.firmware,
            "boot_start": f"0x{self.boot_start:x}",
            "boot_size": self.boot_size,
            "recovery_start": f"0x{self.recovery_start:x}",
            "recovery_size": self.recovery_size,
            "system_start": f"0x{self.system_start:x}",
            "system_size": self.system_size,
            "sdcard": self.sdcard,
            "source": self.source,
            "confirmed": self.confirmed,
            "scatter_sha256": self.scatter_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfileCheck:
    profile: UnlockProfile
    scatter: ScatterInfo | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": self.profile.to_dict(),
            "scatter": self.scatter.to_dict() if self.scatter else None,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ReadbackSpec:
    partition: str
    start_address: int
    size_bytes: int
    suggested_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition,
            "start_address": f"0x{self.start_address:x}",
            "size_bytes": self.size_bytes,
            "suggested_name": self.suggested_name,
        }


def display_path(path: Path | str) -> str:
    """Use ``~`` for the home prefix in reports and CLI output."""
    text = str(path)
    home = str(Path.home())
    if home and text.startswith(home):
        return "~" + text[len(home) :]
    return text


@dataclass(frozen=True, slots=True)
class UnlockArtifact:
    kind: ArtifactKind
    path: Path
    size_bytes: int
    sha256: str
    expected_sha256: str | None = None
    source: str = "user_selected"

    @property
    def sha_matches(self) -> bool:
        return self.expected_sha256 is None or self.sha256 == self.expected_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "path": display_path(self.path),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "expected_sha256": self.expected_sha256,
            "sha_matches": self.sha_matches,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class GuidedStep:
    step_id: str
    title: str
    summary: str
    user_action: str
    expected_result: str
    failure_help: str
    automated: bool = False
    artifact_kind: ArtifactKind | None = None
    partition: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "summary": self.summary,
            "user_action": self.user_action,
            "expected_result": self.expected_result,
            "failure_help": self.failure_help,
            "automated": self.automated,
            "artifact_kind": self.artifact_kind.value if self.artifact_kind else None,
            "partition": self.partition,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class UnlockReport:
    session_id: str
    profile: UnlockProfile
    phase: UnlockPhase
    status: str = "IN_PROGRESS"
    artifacts: dict[str, UnlockArtifact] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def artifact(self, kind: ArtifactKind) -> UnlockArtifact | None:
        return self.artifacts.get(kind.value)

    def add_artifact(self, artifact: UnlockArtifact) -> None:
        self.artifacts[artifact.kind.value] = artifact

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "profile": self.profile.to_dict(),
            "phase": self.phase.value,
            "status": self.status,
            "artifacts": {name: item.to_dict() for name, item in sorted(self.artifacts.items())},
            "checks": dict(self.checks),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }

    def to_markdown(self) -> str:
        lines = [
            "# MCC Unlocker — rapport de déblocage guidé",
            "",
            f"- Session : `{self.session_id}`",
            f"- Profil : `{self.profile.profile_id}` (firmware `{self.profile.firmware}`)",
            f"- Phase : `{self.phase.value}`",
            f"- Statut : `{self.status}`",
            f"- Créé : `{self.created_at}`",
            "",
            "## Preuves",
            "",
        ]
        if not self.artifacts:
            lines.append("Aucun artefact vérifié.")
        for name, artifact in sorted(self.artifacts.items()):
            lines.append(
                f"- **{name}** : `{display_path(artifact.path)}` — {artifact.size_bytes} octets — "
                f"SHA-256 `{artifact.sha256}`"
            )
        lines.extend(["", "## Contrôles", ""])
        if not self.checks:
            lines.append("Aucun contrôle enregistré.")
        for key, value in sorted(self.checks.items()):
            lines.append(f"- `{key}` : {value}")
        if self.warnings:
            lines.extend(["", "## Avertissements", ""])
            for warning in self.warnings:
                lines.append(f"- {warning}")
        lines.extend(["", "## Limites", ""])
        for limitation in self.limitations or [
            "Aucune preuve bit-à-bit des partitions finales n'est incluse dans ce rapport.",
            "La validation réelle sur le robot de référence reste à effectuer.",
        ]:
            lines.append(f"- {limitation}")
        lines.append("")
        return "\n".join(lines)


def canonical_json(value: Any) -> Any:
    """Small helper used by reports/tests to keep enums serialisable."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): canonical_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_json(item) for item in value]
    return value
