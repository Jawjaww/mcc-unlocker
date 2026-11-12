"""Stable error catalogue for the guided unlock application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    ERR_ENV_ADB_MISSING = "ERR_ENV_ADB_MISSING"
    ERR_ENV_STORAGE_PERMISSION = "ERR_ENV_STORAGE_PERMISSION"
    ERR_ADB_NOT_AVAILABLE = "ERR_ADB_NOT_AVAILABLE"
    ERR_ADB_TIMEOUT = "ERR_ADB_TIMEOUT"
    ERR_ADB_UNAUTHORIZED = "ERR_ADB_UNAUTHORIZED"
    ERR_ADB_COMMAND_FAILED = "ERR_ADB_COMMAND_FAILED"
    ERR_JOURNAL_UNAVAILABLE = "ERR_JOURNAL_UNAVAILABLE"
    ERR_PRECONDITION_NOT_MET = "ERR_PRECONDITION_NOT_MET"
    ERR_CANCELLED = "ERR_CANCELLED"
    ERR_INTERNAL = "ERR_INTERNAL"
    ERR_UNLOCK_PROFILE_INVALID = "ERR_UNLOCK_PROFILE_INVALID"
    ERR_UNLOCK_ARTIFACT_INVALID = "ERR_UNLOCK_ARTIFACT_INVALID"
    ERR_UNLOCK_STEP_OUT_OF_ORDER = "ERR_UNLOCK_STEP_OUT_OF_ORDER"
    ERR_UNLOCK_TWRP_UNAVAILABLE = "ERR_UNLOCK_TWRP_UNAVAILABLE"
    ERR_UNLOCK_SYSTEM_MOUNT_FAILED = "ERR_UNLOCK_SYSTEM_MOUNT_FAILED"
    ERR_UNLOCK_SYSTEM_PATCH_FAILED = "ERR_UNLOCK_SYSTEM_PATCH_FAILED"
    ERR_UNLOCK_SDCARD_UNAVAILABLE = "ERR_UNLOCK_SDCARD_UNAVAILABLE"
    ERR_UNLOCK_NOT_CONFIRMED = "ERR_UNLOCK_NOT_CONFIRMED"
    ERR_UNLOCK_ROLLBACK_FAILED = "ERR_UNLOCK_ROLLBACK_FAILED"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: ErrorCode
    user_message: str
    retryable: bool
    rollback_required: bool = False
    critical: bool = False
    retry_hint: str = ""
    likely_cause: str = ""
    device_state: str = "unknown"
    allowed_actions: tuple[str, ...] = ()
    restore_preconditions: tuple[str, ...] = ()


_SPECS: tuple[ErrorSpec, ...] = (
    ErrorSpec(
        ErrorCode.ERR_ENV_ADB_MISSING,
        "Le binaire ADB est introuvable.",
        True,
        retry_hint="Installe Android platform-tools et ajoute adb.exe au PATH.",
    ),
    ErrorSpec(
        ErrorCode.ERR_ENV_STORAGE_PERMISSION,
        "Impossible d'écrire dans le dossier de travail.",
        True,
        retry_hint="Choisis un dossier accessible en écriture.",
    ),
    ErrorSpec(
        ErrorCode.ERR_ADB_NOT_AVAILABLE,
        "ADB n'est pas disponible sur le robot.",
        True,
        retry_hint="Vérifie le câble USB, TWRP et l'autorisation ADB.",
    ),
    ErrorSpec(
        ErrorCode.ERR_ADB_TIMEOUT,
        "ADB ne répond pas dans le délai imparti.",
        True,
        retry_hint="Attends le démarrage de TWRP, puis réessaie.",
    ),
    ErrorSpec(
        ErrorCode.ERR_ADB_UNAUTHORIZED,
        "Autorisation ADB refusée.",
        True,
        retry_hint="Accepte l'autorisation sur l'écran du robot.",
    ),
    ErrorSpec(
        ErrorCode.ERR_ADB_COMMAND_FAILED,
        "Une commande ADB a échoué.",
        True,
        retry_hint="Consulte le journal ; ne poursuis pas une écriture incertaine.",
    ),
    ErrorSpec(
        ErrorCode.ERR_JOURNAL_UNAVAILABLE,
        "Journal durable indisponible.",
        False,
        retry_hint="Choisis un dossier accessible en écriture.",
    ),
    ErrorSpec(
        ErrorCode.ERR_PRECONDITION_NOT_MET,
        "Précondition non remplie pour cette étape.",
        False,
        retry_hint="Termine l'étape précédente.",
    ),
    ErrorSpec(ErrorCode.ERR_CANCELLED, "Opération annulée.", False),
    ErrorSpec(
        ErrorCode.ERR_INTERNAL,
        "Erreur interne inattendue.",
        True,
        retry_hint="Consulte les journaux et réessaie.",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_PROFILE_INVALID,
        "Le profil ou le scatter ne correspond pas à l'appareil attendu.",
        False,
        retry_hint="Utilise le scatter du modèle exact ; aucune écriture n'a eu lieu.",
        device_state="aucune écriture effectuée",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_ARTIFACT_INVALID,
        "Le fichier de sauvegarde ou l'image TWRP ne correspond pas à l'empreinte attendue.",
        False,
        retry_hint="Sélectionne le fichier exact ; ne renomme pas un fichier inconnu.",
        device_state="aucune écriture effectuée",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_STEP_OUT_OF_ORDER,
        "Cette étape ne peut pas être exécutée dans l'état actuel.",
        False,
        retry_hint="Termine l'étape précédente.",
        device_state="aucune nouvelle écriture effectuée",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_TWRP_UNAVAILABLE,
        "TWRP n'est pas accessible en ADB.",
        True,
        retry_hint="Vérifie que le robot a démarré sur TWRP et que le câble USB est branché.",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_SYSTEM_MOUNT_FAILED,
        "Impossible de monter /system en lecture-écriture.",
        False,
        retry_hint="Essaie remountrw puis le remontage explicite ; sinon arrête-toi.",
        device_state="/system non modifié",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_SYSTEM_PATCH_FAILED,
        "Le patch de /system/build.prop a échoué ou n'a pas été vérifié.",
        False,
        retry_hint="Restaure build.prop.bak ; ne redémarre pas avant vérification.",
        device_state="/system potentiellement modifié",
        allowed_actions=("restore_build_prop", "export_journal"),
        restore_preconditions=("build.prop.bak vérifié", "TWRP accessible"),
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_SDCARD_UNAVAILABLE,
        "Le stockage TWRP /sdcard n'est pas accessible.",
        False,
        retry_hint="Vérifie le montage du stockage dans TWRP.",
        device_state="aucune écriture de partition effectuée",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_NOT_CONFIRMED,
        "L'action utilisateur requise n'a pas été confirmée.",
        False,
        retry_hint="Effectue l'action dans SP Flash Tool ou TWRP, puis confirme.",
        device_state="action non exécutée ou non confirmée",
    ),
    ErrorSpec(
        ErrorCode.ERR_UNLOCK_ROLLBACK_FAILED,
        "La restauration du boot ou des fichiers système a échoué.",
        False,
        rollback_required=True,
        critical=True,
        retry_hint="Conserve le câble et suis les instructions SP Flash Tool.",
        likely_cause="Appareil inaccessible, backup invalide ou écriture instable.",
        device_state="critique, état réel inconnu",
        allowed_actions=("manual_recovery", "export_journal"),
        restore_preconditions=("appareil accessible", "backup boot vérifié", "SP Flash Tool disponible"),
    ),
)

ERRORS: dict[ErrorCode, ErrorSpec] = {spec.code: spec for spec in _SPECS}


def err(code: ErrorCode, message: str = "", **details) -> "Err":  # noqa: F821
    from .result import Err

    return Err(code=code, message=message, details=details)


def all_codes() -> tuple[ErrorCode, ...]:
    return tuple(ErrorCode)


__all__ = ["ERRORS", "ErrorCode", "ErrorSpec", "all_codes", "err"]
