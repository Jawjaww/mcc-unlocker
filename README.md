# MCC Unlocker — guided SP Flash Tool + TWRP

Application Windows qui guide le déblocage d'un Monsieur Cuisine Connect
compatible, en s'appuyant sur la procédure communautaire **SP Flash Tool +
TWRP**.

> **Statut : non validé sur le robot de référence.** Le firmware 4921, le
> scatter réel, TWRP et la procédure complète doivent encore être vérifiés en
> M0. Le produit n'est pas terminé et ne doit pas être présenté comme un
> « one-click » fiable.

## Le parcours en 7 écrans

1. **Commencer** — comprendre le but et vérifier ADB.
2. **Brancher le robot** — trappe Torx, port droit « Android USB ».
3. **Sauvegarder le démarrage** — copie obligatoire avant toute modification.
4. **Démarrer TWRP** — TWRP est indispensable : c'est lui qui permet de modifier
   les réglages Android et de garder le robot réparable.
5. **Autoriser ADB** — sauvegarde des réglages, confirmation explicite, puis
   modification vérifiée.
6. **Remettre le démarrage et garder TWRP** — boot original dans `boot`, TWRP
   dans `recovery`, deux Install Image dans TWRP GUI.
7. **Redémarrer et vérifier** — MCC, ADB et TWRP accessibles.

TWRP n'est pas un « outil de secours » optionnel : sans lui, le patch système
n'est pas possible, et il reste ensuite l'environnement de maintenance.

## Ce qu'elle ne fait pas

- Elle n'écrit pas TWRP : elle utilise l'image communautaire fournie/épinglée.
- Elle n'automatise pas SP Flash Tool : c'est un outil GUI externe.
- Elle ne flashe pas `preloader`, `lk`, `tee`, `seccfg`, `userdata` ou `nvram`.
- Elle ne débloque pas le bootloader et ne contourne aucune sécurité.
- Elle n'installe pas l'ancienne APK privée de recettes.
- Elle n'écrit pas dans la base officielle des recettes.
- Elle ne promet pas de preuve bit-à-bit des partitions finales.

## Prérequis

- Windows 10/11 x64.
- Robot de référence, câble USB-A mâle/mâle, port **droit « Android USB »**.
- Tournevis Torx pour la trappe.
- SP Flash Tool + pilote MediaTek/VCOM.
- Android platform-tools (`adb.exe`).
- Un scatter et une image TWRP dont la provenance est vérifiée.

## Installer Windows (release)

Télécharger l'installateur depuis la release :

```powershell
$url = "https://github.com/Jawjaww/mcc-unlocker/releases/download/v0.2.0/MCC-Unlocker-Setup-0.2.0.exe"
$out = "$env:USERPROFILE\Downloads\MCC-Unlocker-Setup-0.2.0.exe"
Invoke-WebRequest -Uri $url -OutFile $out
Get-FileHash $out -Algorithm SHA256
Start-Process $out
```

SHA-256 attendu :
`HASH_APRÈS_BUILD_0.2.0`

Le build est **non signé** : SmartScreen peut demander une confirmation. Il ne
contient pas TWRP, SP Flash Tool, ADB ni les pilotes. Il ne remplace pas M0.

## Démarrage rapide (source)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui]"
.venv\Scripts\python -m mcc_unlocker ui
```

Sous macOS/Linux, le même code sert au développement hors matériel :

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev,gui]"
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
.venv/bin/mcc-unlocker unlock plan
```

## Assets communautaires

Le dépôt de référence peut être cloné localement (il n'est pas versionné ici) :

```bash
git clone --depth 1 https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack.git \
  vendor/Monsieur-Cuisine-Connect-Hack
```

L'application détecte alors `hacks/recovery.img` et
`informations/l706_dfbh_v_695scatter.txt`. Sinon :

```bash
python scripts/fetch_unlock_assets.py --accept-provenance
```

Les assets sont stockés dans `~/.mcc-unlocker/assets/` ; ils ne sont pas
redistribués par l'installateur. Le hash attendu de TWRP est
`fc9ac999fc3b0a6c0cb563f39359084a6fcc211aeb42e7b754990afa4b543d3e`
(taille `11 452 416` octets). Cette image est un `Android bootimg` ; sa
provenance ne prouve pas qu'elle démarre sur le firmware 4921.

## Commandes

```bash
mcc-unlocker ui
mcc-unlocker unlock plan [--scatter ...]
mcc-unlocker unlock verify boot /chemin/boot_backup.img
mcc-unlocker unlock verify twrp /chemin/twrp_recovery.img --sha256 <hash>
```

Le patch système est une commande avancée, avec confirmations explicites ; il
ne flashe pas boot/recovery :

```bash
mcc-unlocker unlock patch \
  --serial <appareil_vérifié> \
  --scatter <scatter> \
  --boot-backup <boot_backup.img> \
  --twrp <twrp_recovery.img> \
  --twrp-boot-flashed --confirm
```

## Tests

```bash
pytest -q
```

Les tests utilisent des faux ADB/TWRP. **Aucun test ne flashe un appareil.**
Le dernier résultat local est indiqué dans [`docs/traceability.md`](docs/traceability.md).

## Documentation

- [Parcours utilisateur — 7 écrans](docs/ux.md)
- [Procédure et limites](docs/unlock-v1.md)
- [Windows, packaging et lancement](docs/windows.md)
- [Sécurité](docs/security.md)
- [Modes de panne](docs/failure-modes.md)
- [Architecture](docs/architecture.md)
- [Outils et mises à jour](docs/tools.md)
- [Traçabilité](docs/traceability.md)

## Licence

MIT. Projet indépendant, non affilié à Monsieur Cuisine / MediaMarkt.
