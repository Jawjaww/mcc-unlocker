"""Parser and validators for the SP Flash Tool scatter file.

The scatter is a *declared* profile, not a live partition table. It is checked
against the reference values before any guided write. No hardware code lives
here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from .models import (
    ArtifactKind,
    ProfileCheck,
    ReadbackSpec,
    ScatterInfo,
    ScatterPartition,
    UnlockArtifact,
    UnlockProfile,
)
from ..utils.hashing import sha256_file


def _number(value: str, field: str) -> int:
    text = value.strip().strip('"').strip("'")
    try:
        return int(text, 0)
    except ValueError as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc


def parse_scatter(text: str, *, sha256: str | None = None) -> Result[ScatterInfo]:
    """Parse the small subset of the MediaTek scatter format we need.

    Only ``project``/``platform`` and partition blocks are used. Unknown keys are
    ignored, so a future scatter revision can still be inspected.
    """
    project = ""
    platform = ""
    current: dict[str, str] | None = None
    partitions: dict[str, ScatterPartition] = {}
    saw_general = False

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        name = current.get("partition_name", "").strip()
        if not name:
            current = None
            return
        try:
            start = _number(current.get("linear_start_addr", ""), "linear_start_addr")
            size = _number(current.get("partition_size", ""), "partition_size")
        except ValueError as exc:
            raise ValueError(f"partition {name}: {exc}") from exc
        partitions[name] = ScatterPartition(
            name=name,
            start_address=start,
            size_bytes=size,
            region=current.get("region", "").strip(),
        )
        current = None

    try:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- general"):
                saw_general = True
                current = None
                continue
            if line.startswith("- partition_index"):
                finish()
                current = {}
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if current is not None:
                current[key] = value
            elif key == "project":
                project = value
            elif key == "platform":
                platform = value
        finish()
    except ValueError as exc:
        return Err(ErrorCode.ERR_UNLOCK_PROFILE_INVALID, details={"reason": str(exc)})

    if not saw_general:
        return Err(
            ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
            details={"reason": "scatter has no general section"},
        )
    if not project or not platform:
        return Err(
            ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
            details={"reason": "scatter project/platform missing"},
        )
    if not partitions:
        return Err(
            ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
            details={"reason": "scatter has no partitions"},
        )
    return Ok(ScatterInfo(project=project, platform=platform, partitions=partitions, sha256=sha256))


def validate_profile(
    profile: UnlockProfile,
    scatter_text: str,
    *,
    expected_scatter_sha256: str | None = None,
    require_system: bool = True,
) -> ProfileCheck:
    actual_sha = hashlib.sha256(scatter_text.encode("utf-8")).hexdigest()
    parsed = parse_scatter(scatter_text, sha256=actual_sha)
    if isinstance(parsed, Err):
        return ProfileCheck(profile=profile, scatter=None, errors=(parsed.message,))
    scatter = parsed.value
    errors: list[str] = []
    warnings: list[str] = []

    if expected_scatter_sha256 and actual_sha != expected_scatter_sha256:
        errors.append("scatter SHA-256 does not match the pinned value")
    if scatter.project != profile.project:
        errors.append(f"project mismatch: {scatter.project!r} != {profile.project!r}")
    if scatter.platform != profile.platform:
        errors.append(f"platform mismatch: {scatter.platform!r} != {profile.platform!r}")

    expected = {
        "boot": (profile.boot_start, profile.boot_size),
        "recovery": (profile.recovery_start, profile.recovery_size),
        "system": (profile.system_start, profile.system_size),
    }
    required = ("boot", "recovery", "system") if require_system else ("boot", "recovery")
    for name in required:
        part = scatter.partition(name)
        if part is None:
            errors.append(f"required partition missing from scatter: {name}")
            continue
        start, size = expected[name]
        if part.start_address != start:
            errors.append(
                f"{name} start mismatch: 0x{part.start_address:x} != 0x{start:x}"
            )
        if part.size_bytes != size:
            errors.append(f"{name} size mismatch: 0x{part.size_bytes:x} != 0x{size:x}")
    if not profile.confirmed:
        warnings.append(
            "profil déclaré, non confirmé sur le robot : vérifier le scatter et le firmware avant écriture"
        )
    return ProfileCheck(profile=profile, scatter=scatter, errors=tuple(errors), warnings=tuple(warnings))


def readback_spec(scatter: ScatterInfo, partition: str) -> Result[ReadbackSpec]:
    part = scatter.partition(partition)
    if part is None:
        return Err(
            ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
            details={"partition": partition, "reason": "not in scatter"},
        )
    return Ok(
        ReadbackSpec(
            partition=partition,
            start_address=part.start_address,
            size_bytes=part.size_bytes,
            suggested_name=f"{partition}_readback.img",
        )
    )


def validate_readback_file(
    path: Path | str,
    spec: ReadbackSpec,
    *,
    expected_sha256: str | None = None,
) -> Result[UnlockArtifact]:
    source = Path(path).expanduser()
    try:
        stat = source.stat()
    except OSError as exc:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"path": str(source), "reason": "file missing", "error": str(exc)},
        )
    if not source.is_file():
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"path": str(source), "reason": "not a regular file"},
        )
    if stat.st_size != spec.size_bytes:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={
                "partition": spec.partition,
                "expected_size": spec.size_bytes,
                "actual_size": stat.st_size,
            },
        )
    actual = sha256_file(source)
    if expected_sha256 and actual != expected_sha256:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={
                "partition": spec.partition,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual,
            },
        )
    return Ok(
        UnlockArtifact(
            kind=ArtifactKind.READBACK_CONTROL,
            path=source,
            size_bytes=stat.st_size,
            sha256=actual,
            expected_sha256=expected_sha256,
        )
    )


def validate_image(path: Path | str, *, expected_sha256: str | None = None) -> Result[UnlockArtifact]:
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            raise OSError("not a regular file")
        size = source.stat().st_size
        actual = sha256_file(source)
    except OSError as exc:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"path": str(source), "reason": "image missing", "error": str(exc)},
        )
    if expected_sha256 and actual != expected_sha256:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"expected_sha256": expected_sha256, "actual_sha256": actual},
        )
    return Ok(
        UnlockArtifact(
            kind=ArtifactKind.TWRP_IMAGE,
            path=source,
            size_bytes=size,
            sha256=actual,
            expected_sha256=expected_sha256,
        )
    )
