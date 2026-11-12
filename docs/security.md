# Sécurité

## Modèle de menace

- Un scatter, un backup ou une image TWRP incorrects peuvent bricker le robot.
- Une modification partielle de `/system/build.prop` peut empêcher ADB.
- SP Flash Tool, TWRP et les pilotes sont des composants externes.
- Les backups et journaux peuvent contenir des données locales.

## Contrôles

- Backup `boot` obligatoire, taille et SHA-256 vérifiés avant toute écriture.
- Image TWRP vérifiée par taille/hash ; provenance à confirmer.
- Scatter comparé au modèle attendu ; refus si divergence.
- Aucune écriture de `preloader`, `lk`, `tee`, `seccfg`, `userdata`, `nvram`.
- `build.prop` sauvegardé, patch idempotent, relu.
- `recovery-from-boot.p` sauvegardé avant suppression.
- Test d'écriture réel avant de modifier `/system`.
- Rollback `boot` via SP Flash ; restauration des fichiers système si TWRP est
  accessible.
- Aucun mot de passe, jeton ou identifiant personnel dans les rapports.
- Aucune télémétrie.

## Limites

- Aucune preuve bit-à-bit des partitions finales dans la v1.
- Aucun contournement de sécurité matérielle.
- Le succès fonctionnel n'est pas une validation de sécurité exhaustive.
