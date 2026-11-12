# Parcours utilisateur — 7 écrans

Le parcours est volontairement court. Chaque écran a une seule action principale.

| # | Écran | Question de l'utilisateur | Réponse de l'écran |
|---|---|---|---|
| 1 | Commencer | « Qu'est-ce que je vais faire ? » | But, risque, trois confirmations, ADB détecté |
| 2 | Brancher | « Où brancher ? » | Robot éteint, trappe Torx, port droit |
| 3 | Sauvegarder | « Pourquoi une sauvegarde ? » | Copie obligatoire avant modification |
| 4 | Démarrer TWRP | « Pourquoi TWRP ? » | TWRP est indispensable pour modifier et réparer |
| 5 | Autoriser ADB | « Qu'est-ce qui change ? » | Résumé clair + confirmation avant écriture |
| 6 | Remettre le démarrage | « Comment garder TWRP ? » | Boot original + TWRP recovery, deux Install Image |
| 7 | Vérifier | « Est-ce que ça marche ? » | MCC, ADB, TWRP, deux redémarrages |

## Règles

- Une action principale par écran.
- Les détails techniques sont repliés.
- Aucune écriture sans confirmation distincte.
- Aucun passage sans preuve (fichier, TWRP, ADB).
- TWRP n'est jamais présenté comme un « secours » : c'est l'outil de maintenance principal.
- Le root n'est pas installé automatiquement ; TWRP permet de le faire ensuite.
