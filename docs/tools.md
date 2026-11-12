# Outils externes, versions et mises à jour

## Principe

Aucun outil ne doit être mis à jour ou remplacé **automatiquement**. Une mise à
jour silencieuse de TWRP, du scatter, d'ADB ou du pilote peut rendre la
procédure incompatible avec le robot.

L'application :

- détecte les outils présents ;
- vérifie les hash/taille des assets épinglés ;
- affiche la provenance ;
- refuse un fichier non conforme ;
- ne télécharge rien sans action explicite.

## Tableau

| Outil | Fourniture | Vérification | Mise à jour |
|---|---|---|---|
| ADB (`adb.exe`) | Android platform-tools, installé par l'utilisateur | présence + version | manuelle, jamais silencieuse |
| SP Flash Tool | installé par l'utilisateur | présence/chemin si configuré | manuelle |
| Pilote MediaTek | installé avec consentement | détection Windows/SP Flash | manuelle |
| TWRP `recovery.img` | asset communautaire épinglé | taille + SHA-256 | **jamais automatique** |
| Scatter | asset communautaire épinglé | taille + SHA-256 + cohérence du profil | **jamais automatique** |

## Faut-il tout linker ?

Non. Un lien direct peut aider, mais il ne doit pas être un bouton
« installer/mettre à jour » qui remplace un asset validé.

- Afficher un lien vers la source et la version épinglée.
- Ne pas télécharger en arrière-plan.
- Ne pas remplacer un fichier existant sans confirmation.
- Après une mise à jour manuelle, recalculer et **relire** le hash avant de
  l'accepter.

## Assets TWRP/scatter

Le dépôt communautaire ne déclare pas de licence de redistribution. Les assets
ne sont donc pas dans l'installateur. Deux voies :

1. cloner le dépôt dans `vendor/Monsieur-Cuisine-Connect-Hack` ;
2. exécuter `python scripts/fetch_unlock_assets.py --accept-provenance`.

Les deux écrivent des fichiers locaux ; aucune mise à jour automatique.

## Mise à jour d'un asset

1. Télécharger manuellement depuis la source.
2. Comparer taille et SHA-256 avec la provenance.
3. Lire les notes de version/commit.
4. Tester en M0 sur un appareil de référence.
5. seulement après, mettre à jour `assets/unlock/provenance.json`.

Une modification de hash sans validation M0 est un changement de procédure, pas
une simple mise à jour.
