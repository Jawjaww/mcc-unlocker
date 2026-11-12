# Architecture

```text
UI PyQt6
  → GuidedUnlockSession
      → SpFlashGuide (guide + validation, aucune I/O robot)
      → TwrpAdb (ADB USB vers TWRP)
          → SystemPatcher (pur, idempotent)
      → UnlockWorkflow (FSM courte, sans I/O)
      → OperationJournal / rapport
  → AdbAdapter (subprocess, USB)
  → CommunityAssets (lecture + hash des assets locaux)
```

- `core/` : `Result/Err`, codes stables.
- `unlock/` : modèle de profil, scatter, guide SP Flash, patch, TWRP, FSM,
  session, assets communautaires.
- `hardware/` : adaptateur ADB.
- `ui/` : fenêtre guidée.
- `utils/` : fichiers atomiques, hash, journal, chemins, ADB discovery.

**Aucun code d'inspection officielle, de base privée, d'APK legacy ou de
mtkclient.** Ces sujets sont hors périmètre de ce dépôt.
