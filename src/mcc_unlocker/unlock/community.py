"""Use the pinned community repository assets when present.

The repository is vendored for local development, but its TWRP image is not
redistributed by this project. This module only reads the files and verifies
their pinned size/SHA-256; it does not claim they boot on the reference device.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from ..utils.paths import project_root

REPO_DIR_NAME = "Monsieur-Cuisine-Connect-Hack"
LOCAL_ASSETS_DIR = Path.home() / ".mcc-unlocker" / "assets"


@dataclass(frozen=True, slots=True)
class CommunityAssets:
    root: Path
    recovery_img: Path
    scatter: Path
    commit: str
    recovery_sha256: str
    scatter_sha256: str
    recovery_size: int
    scatter_size: int

    def to_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "recovery_img": str(self.recovery_img),
            "scatter": str(self.scatter),
            "commit": self.commit,
            "recovery_sha256": self.recovery_sha256,
            "scatter_sha256": self.scatter_sha256,
            "recovery_size": self.recovery_size,
            "scatter_size": self.scatter_size,
        }


def find_community_root() -> Path | None:
    env = os.environ.get("MCC_COMMUNITY_REPO")
    candidates = [
        Path(env).expanduser() if env else None,
        project_root() / "vendor" / REPO_DIR_NAME,
        project_root() / REPO_DIR_NAME,
        Path.home() / ".mcc-unlocker" / "community" / REPO_DIR_NAME,
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "hacks" / "recovery.img").is_file():
            return candidate
    return None


def _provenance() -> dict:
    path = project_root() / "assets" / "unlock" / "provenance.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_community_assets(root: Path | str | None = None) -> Result[CommunityAssets]:
    if root is not None:
        repository = Path(root).expanduser()
    else:
        repository = find_community_root() or LOCAL_ASSETS_DIR
    recovery = repository / "hacks" / "recovery.img"
    scatter = repository / "informations" / "l706_dfbh_v_695scatter.txt"
    if not recovery.is_file() and (repository / "twrp_recovery.img").is_file():
        recovery = repository / "twrp_recovery.img"
        scatter = repository / "l706_dfbh_v_695scatter.txt"
    if not repository.exists():
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"reason": "community repository or local assets not found"},
        )
    if not recovery.is_file() or not scatter.is_file():
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"reason": "community assets missing", "root": str(repository)},
        )
    data = _provenance()
    expected = data["files"]
    recovery_bytes = recovery.read_bytes()
    scatter_bytes = scatter.read_bytes()
    recovery_sha = hashlib.sha256(recovery_bytes).hexdigest()
    scatter_sha = hashlib.sha256(scatter_bytes).hexdigest()
    recovery_entry = expected["twrp_recovery.img"]
    scatter_entry = expected["l706_dfbh_v_695scatter.txt"]
    errors: list[str] = []
    if len(recovery_bytes) != recovery_entry["size_bytes"]:
        errors.append("recovery image size mismatch")
    if recovery_sha != recovery_entry["sha256"]:
        errors.append("recovery image SHA-256 mismatch")
    if len(scatter_bytes) != scatter_entry["size_bytes"]:
        errors.append("scatter size mismatch")
    if scatter_sha != scatter_entry["sha256"]:
        errors.append("scatter SHA-256 mismatch")
    if errors:
        return Err(
            ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
            details={"errors": errors, "root": str(repository)},
        )
    return Ok(
        CommunityAssets(
            root=repository,
            recovery_img=recovery,
            scatter=scatter,
            commit=str(data["commit"]),
            recovery_sha256=recovery_sha,
            scatter_sha256=scatter_sha,
            recovery_size=len(recovery_bytes),
            scatter_size=len(scatter_bytes),
        )
    )


__all__ = ["CommunityAssets", "find_community_root", "load_community_assets"]
