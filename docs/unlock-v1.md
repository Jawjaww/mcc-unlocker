# Procédure de déblocage guidé v1

> **Non validée sur le robot de référence.** Les valeurs du scatter, le
> firmware 4921 et le démarrage de TWRP restent à confirmer en M0.

## Principe

La v1 suit la procédure communautaire documentée :
[EliasKotlyar/Monsieur-Cuisine-Connect-Hack](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack/blob/master/install_en/readme.md).

- SP Flash Tool effectue les readbacks et les flashs BROM.
- TWRP/ADB effectue le patch de `/system/build.prop`.
- TWRP GUI effectue les deux flashs finaux.
- L'application guide, valide les fichiers et vérifie les résultats.
- Aucun moteur TWRP n'est réécrit ; on utilise l'image communautaire.

## Séquence

1. **Sauvegarde `boot`** — SP Flash Tool, onglet Readback :
   ```text
   Start Address: 0x0000000001d20000
   Length:        0x0000000001000000
   Fichier:       boot_backup.img
   ```
   Vérifier d'abord le scatter réel. Le fichier doit faire exactement la taille
   de la partition `boot`.

2. **TWRP dans `boot`** — SP Flash Tool, onglet Download :
   ```text
   Partition: boot
   Fichier:   twrp_recovery.img
   ```
   Redémarrer : TWRP doit apparaître.

3. **Vérification TWRP/ADB** — l'application attend TWRP et vérifie ADB.
   **Aucune modification n'est effectuée à ce stade.**
4. **Confirmation explicite** — l'utilisateur clique sur
   « Sauvegarder et patcher /system » et confirme la boîte de dialogue.
   Sans confirmation, l'état reste `TWRP_READY` et `/system` n'est pas touché.
5. **Patch système** — l'application, via ADB/TWRP :
   ```sh
   mount /system
   remountrw
   # repli :
   mount -o rw,remount /system
   ```
   Elle teste réellement l'écriture, sauvegarde `build.prop` et
   `recovery-from-boot.p`, écrit les propriétés, vérifie, puis supprime
   `recovery-from-boot.p`.

6. **Fichiers finaux** — pousser sous les noms de la référence :
   ```sh
   adb push bootimg.bin /sdcard/
   adb push recovery.bin /sdcard/
   ```
   Dans TWRP : **Install → Install Image** :
   - `bootimg.bin` → `boot` ;
   - `recovery.bin` → `recovery`.

7. **Redémarrage et vérification** : MCC démarre, ADB répond, puis deux
   redémarrages à froid confirment la persistance.

## Propriétés

Une seule occurrence de chaque clé :

```text
persist.service.adb.enable=1
persist.service.debuggable=1
persist.sys.usb.config=mtp,adb
qemu.hw.mainkeys=0
```

## Valeurs du scatter communautaire

Le fichier réel donne :

```text
boot     : 0x1d20000, taille 0x1000000
recovery : 0x2d20000, taille 0x1000000
system   : 0xa800000, taille 0x60000000
```

Ne pas réutiliser ces valeurs pour une autre variante sans vérifier le scatter.

## Rollback

1. Éteindre le robot, reconnecter en BROM.
2. SP Flash Tool + scatter.
3. Flasher `boot_backup.img` dans `boot`.
4. Redémarrer, vérifier MCC + ADB.
5. Si TWRP est accessible : restaurer `build.prop.bak` et
   `recovery-from-boot.p.bak`.
6. La restauration complète de `system.img` est une option avancée.

## M0 — checklist bloquante

1. Confirmer modèle, firmware, scatter, adresses et tailles.
2. Readback `boot` stable et hashé.
3. Flash TWRP dans `boot`, démarrage TWRP, ADB.
4. `mount /system` + `remountrw` + test d'écriture.
5. Patch `build.prop`, suppression `recovery-from-boot.p`, relecture.
6. Flashs finaux TWRP GUI avec `bootimg.bin`/`recovery.bin`.
7. Redémarrage MCC, ADB après deux redémarrages.
8. Rollback `boot` via SP Flash.
9. Validation du chemin `/sdcard`.
10. Vérification des licences/provenances.

## Limites

- Pas de preuve bit-à-bit des partitions finales dans le parcours nominal.
- Pas d'automatisation de SP Flash Tool.
- Pas d'intégration dans la base officielle des recettes.
- Pas de contournement de sécurité ni de contrôle de cuisson.
