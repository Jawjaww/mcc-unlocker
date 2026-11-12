# Traçabilité

Légende : **I** implémenté, **S** testé en simulation, **M** validé matériel,
**B** bloqué.

| # | Exigence | Implémentation | I | S | M | Statut |
|---|---|---|---|---|---|---|
| 1 | Guide SP Flash/TWRP | `unlock/spflash.py`, `docs/unlock-v1.md` | ✅ | ✅ | — | B (M0) |
| 2 | Validation scatter/profil | `unlock/scatter.py` | ✅ | ✅ | — | B (matériel) |
| 3 | Backup boot + hash | `unlock/spflash.py`, session | ✅ | ✅ | — | B (M0) |
| 4 | Patch build.prop idempotent | `unlock/system_patcher.py` | ✅ | ✅ | — | B (TWRP) |
| 5 | Montage + test d'écriture | `unlock/twrp.py` | ✅ | ✅ | — | B (TWRP) |
| 6 | Sauvegarde fichiers système | `unlock/twrp.py`, session | ✅ | ✅ | — | B (M0) |
| 7 | Flashs finaux TWRP GUI | UI/session + confirmations | ✅ | ✅ (UI) | — | B (M0) |
| 8 | Vérification MCC/ADB/persistance | `unlock/workflow.py`, UI | ✅ | ✅ | — | B (robot) |
| 9 | Rollback boot | documentation + guide | ✅ | — | — | B (M0) |
| 10 | Packaging Windows | `scripts/build.py`, Inno, CI | ✅ | ✅ (build dry-run) | — | B (Windows) |

Dernière exécution locale : **43 tests passés** dans ce dépôt propre (unlock +
UI offscreen), plus les tests du dépôt historique. Aucun test matériel.
