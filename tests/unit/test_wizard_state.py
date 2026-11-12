"""Pure gates for the seven-step wizard."""

from __future__ import annotations

from mcc_unlocker.ui.wizard.state import WizardState


def test_start_requires_all_prerequisites():
    state = WizardState()
    assert not state.ready_to_start
    state.owner_confirmed = True
    state.port_confirmed = True
    state.spflash_confirmed = True
    assert not state.ready_to_start
    state.adb_available = True
    assert state.ready_to_start


def test_twrp_requires_backup_and_assets():
    state = WizardState()
    assert not state.ready_for_twrp
    state.boot_backup_verified = True
    state.assets_verified = True
    assert state.ready_for_twrp


def test_finish_requires_mcc_adb_and_twrp():
    state = WizardState()
    assert not state.ready_to_finish
    state.mcc_started = True
    state.adb_verified = True
    assert not state.ready_to_finish
    state.twrp_recovery_verified = True
    assert state.ready_to_finish
