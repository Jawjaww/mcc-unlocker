"""Scatter and artifact validators."""

from __future__ import annotations

import hashlib

from mcc_unlocker.core.errors import ErrorCode
from mcc_unlocker.core.result import Err
from mcc_unlocker.unlock.models import ArtifactKind, UnlockProfile
from mcc_unlocker.unlock.scatter import (
    parse_scatter,
    readback_spec,
    validate_profile,
    validate_readback_file,
)
from mcc_unlocker.unlock.spflash import SpFlashGuide

SCATTER = """\
- general: MTK_PLATFORM_CFG
  info:
    - config_version: V1.1.2
      platform: MT6580
      project: l706_dfbh_v_695
      storage: EMMC

- partition_index: SYS8
  partition_name: boot
  linear_start_addr: 0x1D20000
  partition_size: 0x1000000
  region: EMMC_USER

- partition_index: SYS9
  partition_name: recovery
  linear_start_addr: 0x2D20000
  partition_size: 0x1000000
  region: EMMC_USER

- partition_index: SYS12
  partition_name: system
  linear_start_addr: 0xA800000
  partition_size: 0x60000000
  region: EMMC_USER
"""


def test_parse_scatter_and_profile():
    parsed = parse_scatter(SCATTER)
    assert parsed.is_ok
    info = parsed.value
    assert info.project == "l706_dfbh_v_695"
    assert info.platform == "MT6580"
    assert info.partition("boot").start_address == 0x1D20000
    assert info.partition("system").size_bytes == 0x60000000

    check = validate_profile(UnlockProfile.reference(), SCATTER)
    assert check.ok, check.errors
    assert check.scatter is not None
    assert check.warnings  # declared reference is not a hardware observation


def test_profile_mismatch_is_refused():
    text = SCATTER.replace("0x1D20000", "0x1D20001")
    check = validate_profile(UnlockProfile.reference(), text)
    assert not check.ok
    assert any("boot start" in error for error in check.errors)


def test_scatter_hash_is_checked():
    expected = hashlib.sha256(SCATTER.encode()).hexdigest()
    assert validate_profile(
        UnlockProfile.reference(), SCATTER, expected_scatter_sha256=expected
    ).ok
    assert not validate_profile(
        UnlockProfile.reference(), SCATTER, expected_scatter_sha256="0" * 64
    ).ok


def test_readback_spec_and_size_validation(tmp_path):
    info = parse_scatter(SCATTER).value
    spec = readback_spec(info, "boot")
    assert spec.is_ok
    assert spec.value.size_bytes == 0x1000000
    path = tmp_path / "boot_backup.img"
    path.write_bytes(b"\0" * spec.value.size_bytes)
    checked = validate_readback_file(path, spec.value)
    assert checked.is_ok
    assert checked.value.kind is ArtifactKind.READBACK_CONTROL
    assert checked.value.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_wrong_size_and_hash_are_refused(tmp_path):
    info = parse_scatter(SCATTER).value
    spec = readback_spec(info, "boot").value
    short = tmp_path / "short.img"
    short.write_bytes(b"x")
    result = validate_readback_file(short, spec)
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID
    full = tmp_path / "full.img"
    full.write_bytes(b"\0" * spec.size_bytes)
    result = validate_readback_file(full, spec, expected_sha256="0" * 64)
    assert isinstance(result, Err)


def test_guide_validates_scatter_and_exposes_boot_steps(tmp_path):
    scatter = tmp_path / "scatter.txt"
    scatter.write_text(SCATTER)
    guide = SpFlashGuide(UnlockProfile.reference())
    checked = guide.validate_scatter(scatter)
    assert checked.is_ok
    boot = guide.step("boot_backup")
    assert boot is not None
    assert boot.parameters["start_address"] == "0x01d20000"
    assert "boot_backup.img" in guide.to_markdown()


def test_guide_refuses_bad_scatter(tmp_path):
    scatter = tmp_path / "scatter.txt"
    scatter.write_text(SCATTER.replace("l706_dfbh_v_695", "other_project"))
    result = SpFlashGuide().validate_scatter(scatter)
    assert isinstance(result, Err)
    assert result.code is ErrorCode.ERR_UNLOCK_PROFILE_INVALID
