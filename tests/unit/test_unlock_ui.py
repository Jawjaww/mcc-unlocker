"""Offscreen smoke test for the guided unlock window (no robot)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from mcc_unlocker.ui.unlock_app import QT_AVAILABLE, UnlockWindow
from mcc_unlocker.unlock import (
    GuidedUnlockSession,
    TwrpAdb,
    UnlockProfile,
)
from tests.unlock.test_scatter import SCATTER
from tests.unlock.test_twrp import FakeTwrpTransport, _no_sleep


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_unlock_window_guides_patch_and_final_confirmations(qapp, tmp_path):
    if not QT_AVAILABLE:
        pytest.skip("PyQt6 unavailable")
    scatter = tmp_path / "scatter.txt"
    scatter.write_text(SCATTER)
    boot = tmp_path / "boot_backup.img"
    boot.write_bytes(b"\0" * UnlockProfile.reference().boot_size)
    image = tmp_path / "twrp_recovery.img"
    image.write_bytes(b"TWRP")

    def factory(serial: str, work_dir: Path):
        fake = FakeTwrpTransport()
        twrp = TwrpAdb(fake, serial, sleep=_no_sleep, poll_interval=0)
        return GuidedUnlockSession(UnlockProfile.reference(), work_dir, twrp)

    window = UnlockWindow(
        session_factory=factory,
        device_provider=lambda _adb: [("SERIAL-1234567890", "device")],
        adb_resolver=lambda: "adb",
        out_root=tmp_path / "reports",
        confirm_patch=lambda: True,
    )
    try:
        window.owner_check.setChecked(True)
        window.port_check.setChecked(True)
        window.prereq_check.setChecked(True)
        window.scatter_edit.setText(str(scatter))
        window.boot_edit.setText(str(boot))
        window.twrp_edit.setText(str(image))
        window.twrp_sha_edit.clear()
        window._search_twrp()
        for _ in range(200):
            if window.device_combo.count():
                break
            QTest.qWait(10)
        assert window.device_combo.count() == 1
        window._start()
        for _ in range(400):
            if window.patch_button.isEnabled():
                break
            QTest.qWait(10)
        assert window.patch_button.isEnabled()
        assert window.session is not None
        assert window.session.phase.value == "TWRP_READY"
        window._confirm_patch = lambda: False
        window._patch_system()
        assert window.session.phase.value == "TWRP_READY"
        assert not window.push_button.isEnabled()
        window._confirm_patch = lambda: True
        window._patch_system()
        for _ in range(400):
            if window.push_button.isEnabled():
                break
            QTest.qWait(10)
        assert window.push_button.isEnabled()
        assert window.session.phase.value == "SYSTEM_PATCHED"
        window._push_final()
        for _ in range(200):
            if window.confirm_flash_button.isEnabled():
                break
            QTest.qWait(10)
        assert window.confirm_flash_button.isEnabled()
        window.boot_flash_check.setChecked(True)
        window.recovery_flash_check.setChecked(True)
        window._confirm_flashes()
        assert window.reboot_button.isEnabled()
        window._rebooted()
        assert window.adb_button.isEnabled()
        assert window.session.phase.value == "REBOOTED_ON_MCC"
    finally:
        window.close()
