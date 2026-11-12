# Assets de déblocage

Aucun binaire TWRP, scatter ou pilote n'est versionné ici.

Le dépôt communautaire fournit une image `recovery.img` et un scatter, mais
aucune licence de redistribution explicite n'a été trouvée. Ces fichiers ne
sont donc pas intégrés à l'installateur.

Pour les récupérer localement, avec provenance et hash épinglés :

```bash
python scripts/fetch_unlock_assets.py --accept-provenance
```

Le script écrit dans `~/.mcc-unlocker/assets/`, vérifie le SHA-256 et n'écrase
pas silencieusement un fichier existant. Il ne prouve pas que l'image démarre
sur le firmware 4921 : cette validation est M0.

Le fichier `provenance.json` contient l'URL, le commit, la taille et le hash
attendus. Toute modification de ces valeurs doit être revue.
