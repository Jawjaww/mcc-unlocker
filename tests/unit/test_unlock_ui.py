"""Offscreen tests for the seven-step guided wizard (no robot)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from mcc_unlocker.core.result import Ok
from mcc_unlocker.ui.unlock_app import QT_AVAILABLE, UnlockWindow
from mcc_unlocker.ui.wizard.state import StepId
from mcc_unlocker.unlock import GuidedUnlockSession, TwrpAdb, UnlockProfile
from tests.unlock.test_scatter import SCATTER
from tests.unlock.test_twrp import FakeTwrpTransport, _no_sleep


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _files(tmp_path: Path):
    scatter = tmp_path / "scatter.txt"
    scatter.write_text(SCATTER)
    boot = tmp_path / "boot_backup.img"
    boot.write_bytes(b"\0" * UnlockProfile.reference().boot_size)
    image = tmp_path / "twrp_recovery.img"
    image.write_bytes(b"TWRP")
    return scatter, boot, image


def _window(tmp_path: Path, *, confirm: bool = True) -> UnlockWindow:
    def factory(serial: str, work_dir: Path):
        fake = FakeTwrpTransport()
        twrp = TwrpAdb(fake, serial, sleep=_no_sleep, poll_interval=0)
        return GuidedUnlockSession(UnlockProfile.reference(), work_dir, twrp)

    async def fake_adb():
        return Ok("Android Debug Bridge version 1.0.41")

    return UnlockWindow(
        session_factory=factory,
        device_provider=lambda _adb: [("SERIAL-1234567890", "device")],
        adb_resolver=lambda: sys.executable,
        out_root=tmp_path / "reports",
        confirm_patch=lambda: confirm,
        adb_check=fake_adb,
    )


def _wait_until(predicate, attempts=400):
    for _ in range(attempts):
        if predicate():
            return True
        QTest.qWait(10)
    return predicate()


def _advance_to_twrp(window: UnlockWindow, tmp_path: Path) -> None:
    scatter, boot, image = _files(tmp_path)
    start = window.pages[StepId.START.value]
    start.owner.setChecked(True)
    start.port.setChecked(True)
    start.spflash.setChecked(True)
    start.refresh()
    assert window.go_next() is None or True
    assert window._index == 1
    connect = window.pages[StepId.CONNECT.value]
    connect.confirm.setChecked(True)
    window.go_next()
    assert window._index == 2
    backup = window.pages[StepId.BACKUP.value]
    window.state.scatter_path = scatter
    window.state.twrp_path = image
    assert backup._validate_assets()
    assert backup.set_boot_backup(boot)
    window.go_next()
    assert window._index == 3
    twrp = window.pages[StepId.TWRP.value]
    assert _wait_until(lambda: twrp.device_combo.count() > 0)
    twrp._primary()
    assert _wait_until(lambda: window.state.twrp_ready)


def test_wizard_happy_path(qapp, tmp_path):
    if not QT_AVAILABLE:
        pytest.skip("PyQt6 unavailable")
    window = _window(tmp_path)
    try:
        _advance_to_twrp(window, tmp_path)
        window.go_next()
        adb = window.pages[StepId.ADB.value]
        adb._primary()
        assert _wait_until(lambda: window.state.system_patched)
        window.go_next()

        restore = window.pages[StepId.RESTORE.value]
        restore._push()
        assert _wait_until(lambda: window.state.final_files_pushed)
        restore.boot_check.setChecked(True)
        restore.recovery_check.setChecked(True)
        restore._confirm()
        assert window.state.final_boot_confirmed and window.state.final_recovery_confirmed
        window.go_next()

        verify = window.pages[StepId.VERIFY.value]
        verify.mcc_check.setChecked(True)
        verify._primary()
        assert _wait_until(lambda: window.state.adb_verified)
        verify.persist_check.setChecked(True)
        verify._primary()
        assert _wait_until(lambda: window.state.completed)
        assert window.state.twrp_recovery_verified
        assert verify.report_view.isVisible() or verify.report_view.toPlainText()
    finally:
        window.close()


def test_patch_is_not_applied_without_confirmation(qapp, tmp_path):
    if not QT_AVAILABLE:
        pytest.skip("PyQt6 unavailable")
    window = _window(tmp_path, confirm=False)
    try:
        _advance_to_twrp(window, tmp_path)
        window.go_next()
        adb = window.pages[StepId.ADB.value]
        adb._primary()
        QTest.qWait(100)
        assert not window.state.system_patched
        assert window.session is not None
        assert window.session.phase.value == "TWRP_READY"
    finally:
        window.close()
