# Windows — lancement et packaging

## Lancer depuis les sources

Prérequis : Windows 10/11, Python 3.11+, Android platform-tools, SP Flash Tool
et pilote MediaTek.

```powershell
scripts\run_windows.cmd
```

Le script crée `.venv-win`, installe PyQt6 et ouvre l'assistant. ADB doit être
dans le PATH ou dans `%LOCALAPPDATA%\Android\Sdk\platform-tools`.

## Construire un exécutable

Le binaire Windows doit être construit **sur Windows** : PyInstaller ne
cross-compile pas depuis macOS.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,gui]" pyinstaller
.venv\Scripts\python scripts\build.py
```

Puis, avec Inno Setup 6 :

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows\mcc-unlocker.iss
```

L'installateur ne contient pas TWRP, SP Flash Tool, ADB ni les pilotes : leur
provenance et leur licence doivent être vérifiées. L'application peut les
détecter localement ou l'utilisateur peut les sélectionner.

## CI

`.github/workflows/windows.yml` construit l'exécutable et l'installateur sur
`windows-latest`. La signature Authenticode nécessite un certificat ; sans
certificat, le build est explicitement non signé.

## Limites

- La procédure n'est pas validée sur le firmware 4921 avant M0.
- L'installateur n'est pas un « one-click » : SP Flash Tool et TWRP GUI restent
  des actions utilisateur.
