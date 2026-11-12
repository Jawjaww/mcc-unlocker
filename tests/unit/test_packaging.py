"""Packaging, assets and documentation checks for the clean repository."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from mcc_unlocker.cli import main
from mcc_unlocker.core.result import Err

ROOT = Path(__file__).resolve().parents[2]


def test_info(capsys):
    assert main(["info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["app"] == "MCC Unlocker"
    assert payload["version"] == "0.1.2"


def test_help():
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_build_dry_run():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build.py"), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "PyInstaller" in result.stdout
    assert "MCC-Unlocker" in result.stdout


def test_asset_provenance_and_check_only():
    data = json.loads((ROOT / "assets" / "unlock" / "provenance.json").read_text())
    twrp = data["files"]["twrp_recovery.img"]
    assert twrp["size_bytes"] == 11452416
    assert twrp["sha256"] == "fc9ac999fc3b0a6c0cb563f39359084a6fcc211aeb42e7b754990afa4b543d3e"
    assert twrp["redistributable"] is False
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fetch_unlock_assets.py"), "--check-only"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0
    assert "fc9ac999" in result.stdout


def test_no_images_are_committed():
    assert not list(ROOT.rglob("*.img"))


def test_windows_scripts_and_installer():
    ps1 = (ROOT / "scripts" / "run_windows.ps1").read_text()
    cmd = (ROOT / "scripts" / "run_windows.cmd").read_text()
    iss = (ROOT / "installer" / "windows" / "mcc-unlocker.iss").read_text()
    assert "mcc_unlocker ui" in ps1
    assert "run_windows.ps1" in cmd
    assert "PrivilegesRequired=lowest" in iss
    assert "MCC-Unlocker.exe" in iss


def test_required_docs_and_pyproject():
    for name in ("unlock-v1.md", "windows.md", "security.md", "failure-modes.md", "architecture.md", "traceability.md"):
        assert (ROOT / "docs" / name).is_file(), name
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["mcc-unlocker"] == "mcc_unlocker.cli:main"
    assert data["project"]["version"] == "0.1.2"


def test_clean_repo_has_no_legacy_private_assets():
    assert not (ROOT / "android").exists()
    assert not (ROOT / "assets" / "payloads").exists()
    assert not (ROOT / "src" / "mcc_unlocker" / "recipeservice").exists()
    assert not (ROOT / "src" / "mcc_unlocker" / "services").exists()


def test_local_fetched_assets_are_accepted(tmp_path):
    from mcc_unlocker.unlock.community import load_community_assets

    provenance = json.loads((ROOT / "assets" / "unlock" / "provenance.json").read_text())
    twrp = provenance["files"]["twrp_recovery.img"]
    scatter = provenance["files"]["l706_dfbh_v_695scatter.txt"]
    # Use zero-filled files of the right size only for the parser path; hash
    # validation must still reject them.
    (tmp_path / "twrp_recovery.img").write_bytes(b"\0" * twrp["size_bytes"])
    (tmp_path / "l706_dfbh_v_695scatter.txt").write_bytes(b"\0" * scatter["size_bytes"])
    result = load_community_assets(tmp_path)
    assert isinstance(result, Err)



def test_pyinstaller_entrypoint_runs_without_package_context():
    import os
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "mcc_unlocker" / "__main__.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "unlock" in result.stdout
