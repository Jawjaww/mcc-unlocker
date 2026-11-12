"""Plain-language strings kept separate from page logic."""

APP_TITLE = "MCC Unlocker"

TECH_SPFLASH = """SP Flash Tool — valeurs de référence (à vérifier avec le scatter réel) :
- boot : start 0x0000000001d20000, length 0x0000000001000000
- recovery : start 0x0000000002d20000, length 0x0000000001000000
- system : start 0x000000000a800000, length 0x0000000060000000

L'application ne lance pas SP Flash Tool à ta place.
"""

TECH_ADB = """Commandes réellement exécutées dans TWRP/ADB :
- mount /system
- remountrw
- mount -o rw,remount /system (repli)
- sauvegarde build.prop et recovery-from-boot.p
- écriture des propriétés ADB, relecture, suppression de recovery-from-boot.p
- adb push bootimg.bin /sdcard/
- adb push recovery.bin /sdcard/
"""

TECH_RESTORE = """Dans TWRP GUI :
Install → Install Image → bootimg.bin → partition boot
Install → Install Image → recovery.bin → partition recovery

Ne pas inverser les deux fichiers.
"""

TECH_VERIFY = """Vérifications :
- adb devices doit voir le robot ;
- le robot doit démarrer sur MCC ;
- adb reboot recovery doit afficher TWRP ;
- ADB doit encore répondre après le redémarrage normal.
"""
