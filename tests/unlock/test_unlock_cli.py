"""CLI tests for the guided unlock planner and artifact verifier."""

from __future__ import annotations

import hashlib
import json

from mcc_unlocker.cli import main
from mcc_unlocker.unlock.models import UnlockProfile


def test_unlock_plan_without_scatter_is_safe(tmp_path, capsys):
    out = tmp_path / "plan"
    assert main(["unlock", "plan", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "l706_dfbh_v_695" in text
    assert "Aucune écriture" in text
    payload = json.loads((out / "unlock_plan.json").read_text())
    assert payload["profile"]["confirmed"] is False
    assert len(payload["steps"]) == 10
    assert (out / "unlock_plan.md").is_file()


def test_unlock_plan_with_scatter_and_json(tmp_path, capsys):
    from tests.unlock.test_scatter import SCATTER

    scatter = tmp_path / "scatter.txt"
    scatter.write_text(SCATTER)
    out = tmp_path / "plan"
    assert main(["unlock", "plan", "--scatter", str(scatter), "--out", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["check"]["ok"] is True
    assert payload["check"]["scatter"]["project"] == "l706_dfbh_v_695"


def test_unlock_verify_boot_backup(tmp_path, capsys):
    path = tmp_path / "boot_backup.img"
    path.write_bytes(b"\0" * UnlockProfile.reference().boot_size)
    assert main(["unlock", "verify", "boot", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "boot_backup"
    assert payload["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_unlock_verify_rejects_wrong_size(tmp_path, capsys):
    path = tmp_path / "boot_backup.img"
    path.write_bytes(b"short")
    assert main(["unlock", "verify", "boot", str(path)]) == 2
    assert "ERR_UNLOCK_ARTIFACT_INVALID" in capsys.readouterr().err


def test_unlock_verify_twrp_hash(tmp_path, capsys):
    path = tmp_path / "twrp.img"
    path.write_bytes(b"twrp-image")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert main(["unlock", "verify", "twrp", str(path), "--sha256", expected]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sha_matches"] is True


def test_unlock_patch_refuses_without_explicit_confirmation(tmp_path, capsys):
    assert main(["unlock", "patch", "--serial", "S", "--scatter", "s", "--boot-backup", "b", "--twrp", "t"]) == 2
    assert "--confirm" in capsys.readouterr().err


def test_unlock_patch_refuses_without_twrp_flash_confirmation(tmp_path, capsys):
    assert main(
        [
            "unlock",
            "patch",
            "--serial",
            "S",
            "--scatter",
            "s",
            "--boot-backup",
            "b",
            "--twrp",
            "t",
            "--confirm",
        ]
    ) == 2
    assert "--twrp-boot-flashed" in capsys.readouterr().err
