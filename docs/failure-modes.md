# Modes de panne

| Code | Sens | Réaction |
|---|---|---|
| `ERR_UNLOCK_PROFILE_INVALID` | Scatter/profil différent | Arrêt avant écriture. |
| `ERR_UNLOCK_ARTIFACT_INVALID` | Backup/TWRP taille ou hash invalide | Refuser l'artefact. |
| `ERR_UNLOCK_STEP_OUT_OF_ORDER` | Étape hors séquence | Indiquer l'étape manquante. |
| `ERR_UNLOCK_TWRP_UNAVAILABLE` | TWRP/ADB absent | Ne pas patcher. |
| `ERR_UNLOCK_SYSTEM_MOUNT_FAILED` | `/system` non inscriptible | `remountrw`, repli, puis arrêt. |
| `ERR_UNLOCK_SYSTEM_PATCH_FAILED` | Patch/relecture incohérent | Restaurer `build.prop.bak`. |
| `ERR_UNLOCK_SDCARD_UNAVAILABLE` | `/sdcard` ou push impossible | Ne pas lancer les flashs finaux. |
| `ERR_UNLOCK_NOT_CONFIRMED` | Action non confirmée | Refuser la transition. |
| `ERR_UNLOCK_ROLLBACK_FAILED` | Restauration échouée | État critique, instructions manuelles. |

Après une coupure : conserver le journal, marquer l'état indéterminé, reconnecter,
réinspecter. Ne pas reprendre automatiquement une écriture.
