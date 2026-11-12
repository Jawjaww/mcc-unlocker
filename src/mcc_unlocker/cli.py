"""Command line for the guided MCC unlock application."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .core.result import Err, Ok
from .hardware.adb_adapter import AdbAdapter
from .unlock import (
    AdbTwrpTransport,
    GuidedUnlockSession,
    SpFlashGuide,
    TwrpAdb,
    UnlockProfile,
    load_community_assets,
)
from .utils.filesystem import atomic_write_json, atomic_write_text


def cmd_unlock_plan(args: argparse.Namespace) -> int:
    profile = UnlockProfile.reference()
    if args.firmware:
        profile = replace(profile, firmware=args.firmware)
    guide = SpFlashGuide(profile)
    community = load_community_assets()
    scatter_path = args.scatter
    if scatter_path is None and community.is_ok:
        scatter_path = str(community.value.scatter)
    check = None
    if scatter_path:
        checked = guide.validate_scatter(scatter_path, expected_sha256=args.scatter_sha256)
        if isinstance(checked, Err):
            print(json.dumps(checked.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
            return 2
        check = checked.value
    out_dir = Path(args.out).expanduser() if args.out else Path.cwd() / "unlock-reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.to_dict(),
        "check": check.to_dict() if check else None,
        "steps": [step.to_dict() for step in guide.steps()],
        "community_assets": community.value.to_dict() if community.is_ok else None,
        "limitations": [
            "Profil de référence déclaré, non confirmé sur le robot.",
            "Aucune preuve bit-à-bit des partitions finales n'est incluse.",
            "La procédure n'est pas validée sur le firmware 4921.",
        ],
    }
    json_path = out_dir / "unlock_plan.json"
    md_path = out_dir / "unlock_plan.md"
    atomic_write_json(json_path, payload)
    atomic_write_text(md_path, guide.to_markdown())
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Profil : {profile.profile_id} (firmware {profile.firmware})")
        print(f"Étapes : {len(guide.steps())}")
        print(f"Plan : {md_path}")
        if check:
            print(f"Scatter : OK ({len(check.scatter.partitions) if check.scatter else 0} partitions)")
            for warning in check.warnings:
                print(f"Avertissement : {warning}")
        else:
            print("Scatter non fourni : profil de référence seulement, non confirmé.")
        if community.is_ok:
            print(f"Assets communautaires : {community.value.root}")
            print(f"TWRP : {community.value.recovery_img}")
        print("Aucune écriture n'a été effectuée.")
    return 0


def cmd_unlock_verify(args: argparse.Namespace) -> int:
    guide = SpFlashGuide(UnlockProfile.reference())
    if args.kind == "boot":
        result = guide.validate_boot_backup(args.path)
    elif args.kind == "twrp":
        result = guide.validate_twrp(args.path, expected_sha256=args.sha256)
    else:
        print("Type inconnu.", file=sys.stderr)
        return 2
    if isinstance(result, Err):
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result.value.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_unlock_patch(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("Refus : --confirm est obligatoire pour modifier /system.", file=sys.stderr)
        return 2
    if not args.twrp_boot_flashed:
        print("Refus : confirme d'abord --twrp-boot-flashed.", file=sys.stderr)
        return 2
    profile = UnlockProfile.reference()
    guide = SpFlashGuide(profile)
    checked = guide.validate_scatter(args.scatter, expected_sha256=args.scatter_sha256)
    if isinstance(checked, Err):
        print(json.dumps(checked.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    work_dir = Path(args.work_dir).expanduser()
    adb = AdbAdapter(args.adb)
    twrp = TwrpAdb(AdbTwrpTransport(adb, args.serial), args.serial)
    session = GuidedUnlockSession(profile, work_dir, twrp)

    async def run():
        consented = session.accept_consent()
        if isinstance(consented, Err):
            return consented
        boot = session.validate_boot_backup(args.boot_backup)
        if isinstance(boot, Err):
            return boot
        image = session.validate_twrp_image(args.twrp, expected_sha256=args.twrp_sha256)
        if isinstance(image, Err):
            return image
        flashed = session.record_twrp_boot_flash()
        if isinstance(flashed, Err):
            return flashed
        ready = await session.wait_for_twrp(args.timeout)
        if isinstance(ready, Err):
            return ready
        patched = await session.patch_system()
        if isinstance(patched, Err):
            return patched
        if args.push_final:
            pushed = await session.push_final_images()
            if isinstance(pushed, Err):
                return pushed
        return Ok(patched.value)

    result = asyncio.run(run())
    if isinstance(result, Err):
        session.mark_indeterminate(result.message)
        session.workflow.save_report(work_dir)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    report = session.workflow.save_report(work_dir)
    print(
        json.dumps(
            {
                "status": "SYSTEM_PATCHED",
                "phase": session.phase.value,
                "report": str(report.value) if isinstance(report, Ok) else None,
                "final_images_pushed": bool(args.push_final),
                "next": "Installer bootimg.bin puis recovery.bin via TWRP GUI, redémarrer et vérifier ADB.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_ui(_args: argparse.Namespace) -> int:
    try:
        from .ui.unlock_app import main as ui_main
    except Exception as exc:  # noqa: BLE001
        print(f"Interface graphique indisponible : {exc}", file=sys.stderr)
        print("Installe PyQt6 : pip install 'mcc-unlocker[gui]'", file=sys.stderr)
        return 2
    return int(ui_main([sys.argv[0]]))


def cmd_info(_args: argparse.Namespace) -> int:
    print(json.dumps({"app": "MCC Unlocker", "version": __version__, "commands": ["unlock", "ui", "info"]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcc-unlocker",
        description="MCC Unlocker — guided SP Flash Tool + TWRP unlock",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    unlock = sub.add_parser("unlock", help="guided SP Flash Tool + TWRP unlock")
    unlock_sub = unlock.add_subparsers(dest="unlock_command", required=True)
    plan = unlock_sub.add_parser("plan", help="show and validate the guided procedure")
    plan.add_argument("--scatter", default=None)
    plan.add_argument("--scatter-sha256", default=None)
    plan.add_argument("--firmware", default=None)
    plan.add_argument("--out", default=None)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=cmd_unlock_plan)

    verify = unlock_sub.add_parser("verify", help="validate a boot backup or TWRP image")
    verify.add_argument("kind", choices=("boot", "twrp"))
    verify.add_argument("path")
    verify.add_argument("--sha256", default=None)
    verify.set_defaults(handler=cmd_unlock_verify)

    patch = unlock_sub.add_parser("patch", help="patch /system/build.prop under TWRP")
    patch.add_argument("--serial", required=True)
    patch.add_argument("--scatter", required=True)
    patch.add_argument("--scatter-sha256", default=None)
    patch.add_argument("--adb", default="adb")
    patch.add_argument("--boot-backup", required=True)
    patch.add_argument("--twrp", required=True)
    patch.add_argument("--twrp-sha256", default=None)
    patch.add_argument("--work-dir", default="unlock-reports/session")
    patch.add_argument("--timeout", type=float, default=120.0)
    patch.add_argument("--twrp-boot-flashed", action="store_true")
    patch.add_argument("--confirm", action="store_true")
    patch.add_argument("--push-final", action="store_true")
    patch.set_defaults(handler=cmd_unlock_patch)

    ui = sub.add_parser("ui", help="launch the guided unlock window")
    ui.set_defaults(handler=cmd_ui)
    info = sub.add_parser("info", help="print build information")
    info.set_defaults(handler=cmd_info)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"Erreur interne : {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
