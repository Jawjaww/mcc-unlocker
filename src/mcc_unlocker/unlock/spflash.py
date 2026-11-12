"""Guided SP Flash Tool steps. No GUI automation, no BROM transport."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from .models import (
    ArtifactKind,
    GuidedStep,
    ProfileCheck,
    ReadbackSpec,
    ScatterInfo,
    UnlockArtifact,
    UnlockProfile,
)
from .scatter import parse_scatter, validate_image, validate_profile, validate_readback_file


_BASE_STEPS: tuple[GuidedStep, ...] = (
    GuidedStep(
        step_id="preflight",
        title="Vérifier Windows, SP Flash Tool et le pilote",
        summary="L'application vérifie l'environnement ; SP Flash Tool reste l'outil qui parle au robot.",
        user_action="Branche le robot éteint sur le port droit « Android USB », puis ouvre SP Flash Tool.",
        expected_result="SP Flash Tool détecte le robot en mode Preloader/BROM.",
        failure_help="Ne branche pas le port gauche. Vérifie le pilote MediaTek et le câble A-A.",
    ),
    GuidedStep(
        step_id="consent",
        title="Confirmer que tu possèdes le robot et acceptes le risque",
        summary="Le déblocage modifie boot, recovery et system. Un brick reste possible.",
        user_action="Lis l'avertissement et confirme explicitement.",
        expected_result="Consentement enregistré dans le journal.",
        failure_help="Si tu n'es pas propriétaire ou si tu refuses le risque, arrête-toi ici.",
    ),
    GuidedStep(
        step_id="boot_backup",
        title="Sauvegarder boot avec SP Flash Tool",
        summary="C'est la sauvegarde obligatoire de la référence : sans elle, aucun flash.",
        user_action=(
            "Dans SP Flash Tool, onglet Readback, ajoute une entrée boot avec l'adresse et la "
            "taille affichées, puis lis la partition dans un fichier boot_backup.img."
        ),
        expected_result="Le fichier sélectionné fait exactement la taille de la partition boot.",
        failure_help="Ne saute pas cette étape. Si SP Flash Tool échoue, débranche, attends, recommence.",
        artifact_kind=ArtifactKind.BOOT_BACKUP,
        partition="boot",
    ),
    GuidedStep(
        step_id="twrp_boot_flash",
        title="Flasher TWRP dans boot",
        summary="SP Flash Tool écrit twrp_recovery.img dans la partition boot pour démarrer TWRP.",
        user_action=(
            "Dans SP Flash Tool, onglet Download, sélectionne twrp_recovery.img pour la partition "
            "boot, puis lance le flash."
        ),
        expected_result="SP Flash Tool termine sans erreur ; le robot redémarre sur TWRP.",
        failure_help="Ne débranche pas pendant le flash. En cas d'échec, restore boot_backup.img.",
        artifact_kind=ArtifactKind.TWRP_IMAGE,
        partition="boot",
    ),
    GuidedStep(
        step_id="twrp_ready",
        title="Vérifier TWRP et ADB",
        summary="L'application attend TWRP puis vérifie qu'ADB répond.",
        user_action="Redémarre le robot et laisse-le démarrer sur TWRP.",
        expected_result="TWRP affiche son interface et `adb devices` renvoie un appareil autorisé.",
        failure_help="Si TWRP ne démarre pas, ne continue pas : restaure boot_backup.img via SP Flash.",
        automated=True,
    ),
    GuidedStep(
        step_id="system_patch",
        title="Sauvegarder puis patcher /system",
        summary="L'application sauvegarde build.prop et recovery-from-boot.p, monte /system en écriture, puis ajoute ADB.",
        user_action="Laisse le robot sous TWRP et branche le câble.",
        expected_result="Les quatre propriétés sont présentes une seule fois et recovery-from-boot.p est absent.",
        failure_help="Si le montage ou la vérification échoue, restore build.prop.bak et arrête-toi.",
        automated=True,
        partition="system",
    ),
    GuidedStep(
        step_id="final_boot",
        title="Restaurer le boot d'origine depuis TWRP",
        summary="TWRP installe bootimg.bin dans la partition boot.",
        user_action=(
            "Dans TWRP : Install → Install Image → sélectionne bootimg.bin → partition boot → "
            "confirme le flash."
        ),
        expected_result="TWRP affiche « Successful ».",
        failure_help="N'installe pas recovery.bin dans boot. En cas d'erreur, restore boot via SP Flash.",
        artifact_kind=ArtifactKind.BOOT_BACKUP,
        partition="boot",
    ),
    GuidedStep(
        step_id="final_recovery",
        title="Installer TWRP en recovery",
        summary="TWRP installe recovery.bin dans la partition recovery.",
        user_action=(
            "Dans TWRP : Install → Install Image → sélectionne recovery.bin → partition recovery → "
            "confirme le flash."
        ),
        expected_result="TWRP affiche « Successful ».",
        failure_help="Si le flash échoue, le déblocage ADB peut rester fonctionnel ; signale-le dans le rapport.",
        artifact_kind=ArtifactKind.TWRP_IMAGE,
        partition="recovery",
    ),
    GuidedStep(
        step_id="reboot_verify",
        title="Redémarrer sur MCC et vérifier ADB",
        summary="Le robot doit démarrer sur le firmware d'origine et répondre en ADB.",
        user_action="Redémarre le robot normalement.",
        expected_result="MCC démarre, l'application officielle fonctionne, ADB répond.",
        failure_help="Si MCC ne démarre pas, restore boot_backup.img via SP Flash.",
        automated=True,
    ),
    GuidedStep(
        step_id="persistence",
        title="Vérifier la persistance",
        summary="Deux redémarrages à froid sont nécessaires pour considérer ADB persistant.",
        user_action="Redémarre deux fois le robot, sans câble de maintenance si possible.",
        expected_result="ADB répond encore après les deux redémarrages.",
        failure_help="Si ADB disparaît, le patch n'est pas persistant : ne déclare pas le succès.",
        automated=True,
    ),
)


class SpFlashGuide:
    """Ordered, read-only guide around the reference procedure."""

    def __init__(self, profile: UnlockProfile | None = None) -> None:
        self.profile = profile or UnlockProfile.reference()

    def steps(self) -> tuple[GuidedStep, ...]:
        boot = self.profile
        return tuple(
            replace(
                step,
                parameters=(
                    {
                        "partition": "boot",
                        "start_address": f"0x{boot.boot_start:08x}",
                        "size_bytes": boot.boot_size,
                        "length": f"0x{boot.boot_size:08x}",
                        "suggested_name": "boot_backup.img",
                    }
                    if step.step_id == "boot_backup"
                    else dict(step.parameters)
                ),
            )
            for step in _BASE_STEPS
        )

    def step(self, step_id: str) -> GuidedStep | None:
        return next((step for step in self.steps() if step.step_id == step_id), None)

    def validate_scatter(
        self,
        path: Path | str,
        *,
        expected_sha256: str | None = None,
    ) -> Result[ProfileCheck]:
        try:
            text = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Err(
                ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
                details={"path": str(path), "reason": "scatter unreadable", "error": str(exc)},
            )
        check = validate_profile(
            self.profile,
            text,
            expected_scatter_sha256=expected_sha256,
            require_system=True,
        )
        if not check.ok:
            return Err(
                ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
                details={"errors": list(check.errors), "warnings": list(check.warnings)},
            )
        return Ok(check)

    def scatter(self, path: Path | str) -> Result[ScatterInfo]:
        try:
            text = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Err(
                ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
                details={"path": str(path), "reason": "scatter unreadable", "error": str(exc)},
            )
        return parse_scatter(text)

    def readback(self, partition: str) -> Result[ReadbackSpec]:
        # The declared profile is enough to display the boot address; a real
        # scatter is still required before any write.
        if partition == "boot":
            return Ok(
                ReadbackSpec(
                    partition="boot",
                    start_address=self.profile.boot_start,
                    size_bytes=self.profile.boot_size,
                    suggested_name="boot_backup.img",
                )
            )
        if partition == "recovery":
            return Ok(
                ReadbackSpec(
                    partition="recovery",
                    start_address=self.profile.recovery_start,
                    size_bytes=self.profile.recovery_size,
                    suggested_name="recovery_original.img",
                )
            )
        if partition == "system":
            return Ok(
                ReadbackSpec(
                    partition="system",
                    start_address=self.profile.system_start,
                    size_bytes=self.profile.system_size,
                    suggested_name="system.img",
                )
            )
        return Err(
            ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
            details={"partition": partition, "reason": "unknown partition"},
        )

    def validate_boot_backup(self, path: Path | str) -> Result[UnlockArtifact]:
        spec = self.readback("boot")
        if isinstance(spec, Err):
            return spec
        checked = validate_readback_file(path, spec.value)
        if isinstance(checked, Err):
            return checked
        return Ok(
            replace(
                checked.value,
                kind=ArtifactKind.BOOT_BACKUP,
                source="sp_flash_readback",
            )
        )

    def validate_twrp(self, path: Path | str, *, expected_sha256: str | None = None) -> Result[UnlockArtifact]:
        return validate_image(path, expected_sha256=expected_sha256)

    def validate_optional_readback(
        self, path: Path | str, partition: str
    ) -> Result[UnlockArtifact]:
        spec = self.readback(partition)
        if isinstance(spec, Err):
            return spec
        return validate_readback_file(path, spec.value)

    def to_markdown(self) -> str:
        lines = [
            "# Guide de déblocage MCC — v1",
            "",
            f"Profil : `{self.profile.profile_id}` — firmware `{self.profile.firmware}`.",
            "",
            "> Procédure de référence : SP Flash Tool, TWRP, patch ADB, restauration TWRP.",
            "> Aucun readback final obligatoire ; la validation reste fonctionnelle.",
            "",
        ]
        for index, step in enumerate(self.steps(), start=1):
            lines.append(f"## {index}. {step.title}")
            lines.append("")
            lines.append(step.summary)
            lines.append("")
            lines.append(f"**Action** : {step.user_action}")
            lines.append("")
            lines.append(f"**Attendu** : {step.expected_result}")
            lines.append("")
            lines.append(f"**Si échec** : {step.failure_help}")
            lines.append("")
        return "\n".join(lines)


__all__ = ["SpFlashGuide"]
