"""UI-only state and gates. No hardware or filesystem writes here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class StepId(str, Enum):
    START = "START"
    CONNECT = "CONNECT"
    BACKUP = "BACKUP"
    TWRP = "TWRP"
    ADB = "ADB"
    RESTORE = "RESTORE"
    VERIFY = "VERIFY"


STEP_ORDER: tuple[StepId, ...] = (
    StepId.START,
    StepId.CONNECT,
    StepId.BACKUP,
    StepId.TWRP,
    StepId.ADB,
    StepId.RESTORE,
    StepId.VERIFY,
)


@dataclass
class WizardState:
    # écran 1
    owner_confirmed: bool = False
    port_confirmed: bool = False
    spflash_confirmed: bool = False
    adb_path: str = ""
    adb_available: bool = False

    # écran 2
    robot_connected: bool = False

    # écran 3
    scatter_path: Path | None = None
    twrp_path: Path | None = None
    boot_backup_path: Path | None = None
    boot_backup_verified: bool = False
    assets_verified: bool = False

    # écran 4
    serial: str = ""
    twrp_ready: bool = False

    # écran 5
    system_patched: bool = False

    # écran 6
    final_files_pushed: bool = False
    final_boot_confirmed: bool = False
    final_recovery_confirmed: bool = False

    # écran 7
    mcc_started: bool = False
    adb_verified: bool = False
    twrp_recovery_verified: bool = False
    completed: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def ready_to_start(self) -> bool:
        return (
            self.owner_confirmed
            and self.port_confirmed
            and self.spflash_confirmed
            and self.adb_available
        )

    @property
    def ready_for_twrp(self) -> bool:
        return self.boot_backup_verified and self.assets_verified

    @property
    def ready_to_finish(self) -> bool:
        return self.mcc_started and self.adb_verified and self.twrp_recovery_verified
