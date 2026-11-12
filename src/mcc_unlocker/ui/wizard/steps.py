"""The seven user-facing steps, each with one primary action."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...core.result import Err, Ok
from ...unlock import SpFlashGuide, UnlockProfile, load_community_assets
from ...utils.filesystem import ensure_dir
from .base import StepPage
from .copy import TECH_ADB, TECH_RESTORE, TECH_SPFLASH, TECH_VERIFY
from .state import StepId

try:  # pragma: no cover - optional PyQt6
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # noqa: BLE001
    QCheckBox = QComboBox = QFileDialog = QGroupBox = QHBoxLayout = QLabel = QLineEdit = QPushButton = QTextBrowser = QVBoxLayout = QWidget = object  # type: ignore[assignment,misc]


class StartPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.START.value,
            "Bienvenue — débloquer ton MCC",
            "Cette application te guide pour rendre le robot accessible en ADB et "
            "installer TWRP. Elle ne clique pas à ta place dans les outils externes.",
        )
        warning = QLabel(
            "<b>Important :</b> la procédure n'est pas encore validée sur le robot "
            "de référence. Un mauvais flash peut endommager l'appareil. "
            "Ne continue que si tu possèdes le robot et acceptes ce risque."
        )
        warning.setWordWrap(True)
        self.add_widget(warning)
        self.tools = QLabel(
            "<b>À installer toi-même avant de commencer :</b><br>"
            "• <a href='https://spflashtool.com/'>SP Flash Tool</a> et le pilote "
            "USB MediaTek/VCOM adapté à ton robot.<br>"
            "• <a href='https://developer.android.com/tools/releases/platform-tools'>"
            "Android Platform Tools (ADB)</a>.<br>"
            "L'application ne les installe pas et ne les met pas à jour. "
            "<a href='https://github.com/Jawjaww/mcc-unlocker/blob/main/docs/tools.md'>"
            "Aide sur les outils</a>."
        )
        self.tools.setOpenExternalLinks(True)
        self.tools.setWordWrap(True)
        self.add_widget(self.tools)
        self.owner = QCheckBox("Je possède ce robot et j'accepte le risque.")
        self.port = QCheckBox("J'utiliserai le port droit « Android USB ».")
        self.spflash = QCheckBox(
            "J'ai installé SP Flash Tool, le pilote USB MediaTek/VCOM et ADB."
        )
        for box in (self.owner, self.port, self.spflash):
            box.stateChanged.connect(self.refresh)
            self.add_widget(box)
        self.adb_status = QLabel("")
        self.adb_status.setWordWrap(True)
        verify = QPushButton("Vérifier ADB")
        verify.clicked.connect(self.refresh)
        adb_row = QHBoxLayout()
        adb_row.addWidget(self.adb_status, 1)
        adb_row.addWidget(verify)
        self.add_layout(adb_row)
        self.set_help(
            "ADB manque ? Utilise le lien Android Platform Tools, ajoute son dossier au "
            "PATH, puis clique sur Vérifier ADB. Pour SP Flash Tool et le pilote "
            "MediaTek : télécharge-les depuis le lien ci-dessus et suis le tutoriel de "
            "ton modèle. L'application ne les installe pas."
        )
        self.set_primary_action(self._primary)
        self.set_primary("Commencer", False)

    def on_enter(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        state = self.window.state
        state.owner_confirmed = self.owner.isChecked()
        state.port_confirmed = self.port.isChecked()
        state.spflash_confirmed = self.spflash.isChecked()
        path = self.window.adb_resolver()
        available = self.window.adb_available()
        state.adb_path = path
        state.adb_available = available
        if available:
            self.adb_status.setText(f"ADB est prêt : {path}")
        else:
            self.adb_status.setText(
                "ADB n'est pas encore détecté. Installe Android Platform Tools, "
                "puis clique sur « Vérifier ADB »."
            )
        self.set_primary("Commencer", state.ready_to_start)

    def _primary(self) -> None:
        if self.window.state.ready_to_start:
            self.window.go_next()
        else:
            self.set_status("Coche les trois cases et vérifie ADB avant de continuer.", error=True)

    def can_leave(self) -> bool:
        return self.window.state.ready_to_start


class ConnectPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.CONNECT.value,
            "Brancher le robot",
            "On prépare la connexion physique. Le robot doit être éteint.",
        )
        self.steps = QLabel(
            "1. Éteins le robot.\n"
            "2. Dévisse la petite trappe sous l'appareil avec un tournevis Torx.\n"
            "3. Branche le câble USB-A mâle/mâle sur le port droit "
            "« Android USB ».\n"
            "4. Ne branche pas le port gauche."
        )
        self.steps.setWordWrap(True)
        self.add_widget(self.steps)
        self.confirm = QCheckBox(
            "Le robot est éteint, la trappe est ouverte et le câble est sur le port droit."
        )
        self.confirm.stateChanged.connect(self.refresh)
        self.add_widget(self.confirm)
        self.set_help(
            "Le port gauche n'est pas un port Android. L'utiliser peut endommager le robot. "
            "Si le câble est mal branché, débranche et recommence robot éteint."
        )
        self.set_primary_action(self._primary)
        self.set_primary("Le robot est branché", False)

    def on_enter(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.window.state.robot_connected = self.confirm.isChecked()
        self.set_primary("Le robot est branché", self.confirm.isChecked())

    def _primary(self) -> None:
        if not self.confirm.isChecked():
            self.set_status("Confirme le branchement avant de continuer.", error=True)
            return
        self.window.state.robot_connected = True
        self.window.go_next()

    def can_leave(self) -> bool:
        return self.window.state.robot_connected


class BackupPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.BACKUP.value,
            "Sauvegarder le démarrage",
            "On garde une copie de secours avant toute modification. C'est la seule "
            "vraie condition de sécurité de cette procédure.",
        )
        self.explain = QLabel(
            "Dans SP Flash Tool, onglet Readback, lis la partition de démarrage. "
            "Puis choisis le fichier obtenu ci-dessous. Si tu n'as pas encore fait "
            "la lecture, le guide ci-dessous te donne les valeurs exactes."
        )
        self.explain.setWordWrap(True)
        self.add_widget(self.explain)
        self.scatter_label = QLabel("")
        self.twrp_label = QLabel("")
        self.boot_label = QLabel("Aucune sauvegarde choisie.")
        for label in (self.scatter_label, self.twrp_label, self.boot_label):
            label.setWordWrap(True)
            self.add_widget(label)
        row = QHBoxLayout()
        self.choose_scatter_button = QPushButton("Choisir le plan du robot")
        self.choose_scatter_button.clicked.connect(self._choose_scatter)
        self.choose_twrp_button = QPushButton("Choisir TWRP")
        self.choose_twrp_button.clicked.connect(self._choose_twrp)
        self.choose_boot_button = QPushButton("Choisir la sauvegarde")
        self.choose_boot_button.clicked.connect(self._choose_boot)
        row.addWidget(self.choose_scatter_button)
        row.addWidget(self.choose_twrp_button)
        row.addWidget(self.choose_boot_button)
        self.add_layout(row)
        self.set_help(
            "SP Flash Tool doit lire exactement la partition de démarrage. Si le fichier "
            "n'a pas la bonne taille, recommence la lecture : ne continue jamais sans "
            "sauvegarde vérifiée."
        )
        self.set_technical(TECH_SPFLASH)
        self.set_primary_action(self._primary)
        self.set_primary("Choisir la sauvegarde", False)

    def on_enter(self) -> None:
        state = self.window.state
        assets = load_community_assets()
        if assets.is_ok:
            state.scatter_path = assets.value.scatter
            state.twrp_path = assets.value.recovery_img
            self.scatter_label.setText(f"Plan du robot : {assets.value.scatter.name} (trouvé)")
            self.twrp_label.setText("TWRP : image communautaire trouvée et épinglée.")
            self.choose_scatter_button.setVisible(False)
            self.choose_twrp_button.setVisible(False)
        else:
            self.scatter_label.setText("Plan du robot : à choisir.")
            self.twrp_label.setText("TWRP : à choisir.")
            self.choose_scatter_button.setVisible(True)
            self.choose_twrp_button.setVisible(True)
        self._validate_assets()
        self.refresh()

    def _validate_assets(self) -> bool:
        state = self.window.state
        guide = SpFlashGuide(UnlockProfile.reference())
        if state.scatter_path is None or state.twrp_path is None:
            state.assets_verified = False
            return False
        scatter = guide.validate_scatter(state.scatter_path)
        twrp = guide.validate_twrp(state.twrp_path)
        state.assets_verified = scatter.is_ok and twrp.is_ok
        return state.assets_verified

    def set_boot_backup(self, path: Path | str) -> bool:
        state = self.window.state
        guide = SpFlashGuide(UnlockProfile.reference())
        result = guide.validate_boot_backup(path)
        if isinstance(result, Err):
            state.boot_backup_verified = False
            self.boot_label.setText(f"Sauvegarde refusée : {result.message}")
            self.set_status("Ce fichier ne correspond pas à la taille de la partition boot.", error=True)
            self.refresh()
            return False
        state.boot_backup_path = Path(path).expanduser()
        state.boot_backup_verified = True
        self.boot_label.setText(f"Sauvegarde vérifiée : {state.boot_backup_path.name}")
        self.set_status("Sauvegarde vérifiée. Tu peux continuer.")
        self.refresh()
        return True

    def _choose_scatter(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Plan du robot", "", "Scatter (*.txt)")
        if path:
            self.window.state.scatter_path = Path(path)
            self.scatter_label.setText(f"Plan du robot : {Path(path).name}")
            self._validate_assets()
            self.refresh()

    def _choose_twrp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Image TWRP", "", "Image (*.img)")
        if path:
            self.window.state.twrp_path = Path(path)
            self.twrp_label.setText(f"TWRP : {Path(path).name}")
            self._validate_assets()
            self.refresh()

    def _choose_boot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Sauvegarde du démarrage", "", "Image (*.img *.bin)")
        if path:
            self.set_boot_backup(path)

    def refresh(self) -> None:
        state = self.window.state
        ready = state.boot_backup_verified and state.assets_verified
        self.set_primary("Continuer" if ready else "Choisir la sauvegarde", ready)

    def _primary(self) -> None:
        if self.window.state.boot_backup_verified and self.window.state.assets_verified:
            self.window.go_next()
        else:
            self._choose_boot()

    def can_leave(self) -> bool:
        return self.window.state.boot_backup_verified and self.window.state.assets_verified


class TwrpPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.TWRP.value,
            "Démarrer TWRP",
            "TWRP est l'outil qui permet de modifier les réglages Android et de garder "
            "le robot réparable. Il est indispensable, pas optionnel.",
        )
        self.explain = QLabel(
            "Flashe TWRP dans la partition de démarrage avec SP Flash Tool, puis "
            "redémarre le robot. L'application va vérifier qu'il est bien accessible."
        )
        self.explain.setWordWrap(True)
        self.add_widget(self.explain)
        self.device_combo = QComboBox()
        self.search_button = QPushButton("Rechercher TWRP")
        self.search_button.clicked.connect(self._search)
        row = QHBoxLayout()
        row.addWidget(self.device_combo, 1)
        row.addWidget(self.search_button)
        self.add_layout(row)
        self.set_help(
            "Si TWRP n'apparaît pas : vérifie que le flash SP Flash a réussi, que le "
            "robot a redémarré, et que le câble est sur le port droit. Ne passe pas à "
            "l'étape suivante sans TWRP."
        )
        self.set_technical(TECH_SPFLASH)
        self.set_primary_action(self._primary)
        self.set_primary("J'ai flashé TWRP", False)

    def on_enter(self) -> None:
        if self.window.state.twrp_ready:
            self.set_status("TWRP est prêt. Aucune modification n'a encore été faite.")
            self.set_primary_action(self._next)
            self.set_primary("Continuer", True)
            return
        self.set_primary_action(self._primary)
        self.set_primary("J'ai flashé TWRP", False)
        self._search()

    def _next(self) -> None:
        self.window.go_next()

    def _search(self) -> None:
        path = self.window.adb_resolver()
        self.window.run_devices(path, self._devices)

    def _devices(self, result) -> None:
        self.device_combo.clear()
        if isinstance(result, Err):
            self.set_status(result.message, error=True)
            return
        items = result.value if isinstance(result, Ok) else result
        if not isinstance(items, (list, tuple)):
            items = []
        for serial, status in items:
            if status == "device":
                self.device_combo.addItem(self.window.mask_serial(serial), serial)
        if self.device_combo.count():
            self.set_status("TWRP est visible. Clique sur « J'ai flashé TWRP ».")
            self.set_primary("J'ai flashé TWRP", True)
        else:
            self.set_status("TWRP n'est pas encore visible. Termine le flash puis réessaie.", error=True)
            self.set_primary("J'ai flashé TWRP", False)

    def _primary(self) -> None:
        serial = self.device_combo.currentData()
        if not serial:
            self.set_status("Sélectionne le robot TWRP détecté.", error=True)
            return
        state = self.window.state
        if not (state.boot_backup_path and state.twrp_path):
            self.set_status("Les fichiers de l'étape 3 sont incomplets.", error=True)
            return
        work_dir = ensure_dir(self.window.work_root / f"unlock-{datetime.now().strftime('%Y%m%dT%H%M%S')}")
        session = self.window.session_factory(str(serial), work_dir)
        self.window.session = session
        consent = session.accept_consent()
        if isinstance(consent, Err):
            self.set_status(consent.message, error=True)
            return
        boot = session.validate_boot_backup(state.boot_backup_path)
        if isinstance(boot, Err):
            self.set_status(boot.message, error=True)
            return
        image = session.validate_twrp_image(state.twrp_path)
        if isinstance(image, Err):
            self.set_status(image.message, error=True)
            return
        flashed = session.record_twrp_boot_flash()
        if isinstance(flashed, Err):
            self.set_status(flashed.message, error=True)
            return
        state.serial = str(serial)
        self.set_status("Recherche de TWRP en cours…")
        self.window.run_async(session.wait_for_twrp, self._ready)

    def _ready(self, result) -> None:
        self.window.set_busy(False)
        if isinstance(result, Err):
            self.set_status(f"TWRP n'est pas accessible : {result.message}", error=True)
            self.set_primary("Réessayer", True)
            return
        self.window.state.twrp_ready = True
        self.set_status("TWRP est prêt. Aucune modification n'a été faite.")
        self.set_primary_action(self._next)
        self.set_primary("Continuer", True)

    def can_leave(self) -> bool:
        return self.window.state.twrp_ready


class AdbPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.ADB.value,
            "Autoriser ADB",
            "On va sauvegarder les réglages actuels, puis ajouter les réglages qui "
            "permettent à l'ordinateur de communiquer avec le robot.",
        )
        self.summary = QLabel(
            "L'application sauvegarde les réglages, autorise ADB, garde les boutons "
            "Android et vérifie le résultat. Si tu refuses la confirmation, rien "
            "n'est modifié."
        )
        self.summary.setWordWrap(True)
        self.add_widget(self.summary)
        self.set_help(
            "Si le montage ou la vérification échoue, l'application s'arrête. "
            "Les réglages sauvegardés restent disponibles pour la restauration."
        )
        self.set_technical(TECH_ADB)
        self.set_primary_action(self._primary)
        self.set_primary("Sauvegarder et autoriser ADB", False)

    def on_enter(self) -> None:
        if self.window.state.system_patched:
            self.set_status("Les réglages Android sont déjà modifiés et vérifiés.")
            self.set_primary_action(self._next)
            self.set_primary("Continuer", True)
            return
        if self.window.session is None:
            self.set_status("La session TWRP n'est pas prête.", error=True)
            self.set_primary("Sauvegarder et autoriser ADB", False)
            return
        self.set_primary_action(self._primary)
        self.set_primary("Sauvegarder et autoriser ADB", True)

    def _next(self) -> None:
        self.window.go_next()

    def _primary(self) -> None:
        if self.window.state.system_patched:
            self.window.go_next()
            return
        if self.window.session is None:
            self.set_status("La session TWRP n'est pas prête.", error=True)
            return
        if not self.window.confirm_patch():
            self.set_status("Confirmation refusée. Rien n'a été modifié.")
            return
        self.set_status("Sauvegarde et modification en cours…")
        self.window.run_async(self.window.session.patch_system, self._patched)

    def _patched(self, result) -> None:
        self.window.set_busy(False)
        if isinstance(result, Err):
            self.set_status(f"Le patch a échoué : {result.message}", error=True)
            self.set_primary("Réessayer", True)
            return
        self.window.state.system_patched = True
        self.set_status("Les réglages Android sont sauvegardés, modifiés et vérifiés.")
        self.set_primary_action(self._next)
        self.set_primary("Continuer", True)

    def can_leave(self) -> bool:
        return self.window.state.system_patched


class RestorePage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.RESTORE.value,
            "Remettre le démarrage et garder TWRP",
            "On remet le fichier de démarrage d'origine pour que MCC démarre normalement, "
            "et on installe TWRP dans la partition de maintenance.",
        )
        self.explain = QLabel(
            "L'application prépare les deux fichiers sur le robot. Ensuite, tu les "
            "installes toi-même dans TWRP. TWRP reste indispensable pour la suite."
        )
        self.explain.setWordWrap(True)
        self.add_widget(self.explain)
        self.boot_check = QCheckBox("J'ai installé bootimg.bin dans boot (TWRP a affiché Successful).")
        self.recovery_check = QCheckBox("J'ai installé recovery.bin dans recovery (TWRP a affiché Successful).")
        self.boot_check.setEnabled(False)
        self.recovery_check.setEnabled(False)
        self.boot_check.stateChanged.connect(self.refresh)
        self.recovery_check.stateChanged.connect(self.refresh)
        self.add_widget(self.boot_check)
        self.add_widget(self.recovery_check)
        self.set_help(
            "Ne pas inverser bootimg.bin et recovery.bin. Si TWRP n'affiche pas "
            "Successful, arrête-toi et ne redémarre pas."
        )
        self.set_technical(TECH_RESTORE)
        self.set_primary_action(self._push)
        self.set_primary("Préparer les fichiers", False)

    def on_enter(self) -> None:
        state = self.window.state
        if state.final_boot_confirmed and state.final_recovery_confirmed:
            self.boot_check.setChecked(True)
            self.recovery_check.setChecked(True)
            self.set_primary_action(self._next)
            self.set_primary("Continuer", True)
            return
        if state.final_files_pushed:
            self.boot_check.setEnabled(True)
            self.recovery_check.setEnabled(True)
            self.set_primary_action(self._confirm)
            self.set_primary("J'ai terminé les flashs", False)
            self.refresh()
            return
        self.set_primary_action(self._push)
        self.set_primary("Préparer les fichiers", self.window.session is not None)

    def _push(self) -> None:
        if self.window.session is None:
            self.set_status("La session TWRP n'est pas prête.", error=True)
            return
        self.set_status("Préparation des fichiers sur le robot…")
        self.window.run_async(self.window.session.push_final_images, self._pushed)

    def _pushed(self, result) -> None:
        self.window.set_busy(False)
        if isinstance(result, Err):
            self.set_status(f"Préparation impossible : {result.message}", error=True)
            self.set_primary("Réessayer", True)
            return
        self.window.state.final_files_pushed = True
        self.boot_check.setEnabled(True)
        self.recovery_check.setEnabled(True)
        self.set_status("Les deux fichiers sont sur le robot. Fais les deux Install Image dans TWRP.")
        self.set_primary_action(self._confirm)
        self.set_primary("J'ai terminé les flashs", False)

    def _confirm(self) -> None:
        if not (self.boot_check.isChecked() and self.recovery_check.isChecked()):
            self.set_status("Confirme les deux flashs TWRP.", error=True)
            return
        session = self.window.session
        if session is None:
            self.set_status("La session TWRP n'est pas prête.", error=True)
            return
        result = session.record_final_flashes(
            boot=self.boot_check.isChecked(), recovery=self.recovery_check.isChecked()
        )
        if isinstance(result, Err):
            self.set_status(result.message, error=True)
            return
        self.window.state.final_boot_confirmed = True
        self.window.state.final_recovery_confirmed = True
        self.set_status("Flashs confirmés. Redémarre le robot sur MCC.")
        self.set_primary_action(self._next)
        self.set_primary("Continuer", True)

    def _next(self) -> None:
        self.window.go_next()

    def refresh(self) -> None:
        if self.window.state.final_files_pushed:
            self.set_primary(
                "J'ai terminé les flashs",
                self.boot_check.isChecked() and self.recovery_check.isChecked(),
            )

    def can_leave(self) -> bool:
        return self.window.state.final_boot_confirmed and self.window.state.final_recovery_confirmed


class VerifyPage(StepPage):
    def __init__(self, window) -> None:
        super().__init__(
            window,
            StepId.VERIFY.value,
            "Redémarrer et vérifier",
            "Dernière étape : vérifier que MCC démarre, qu'ADB répond et que TWRP reste "
            "accessible.",
        )
        self.explain = QLabel(
            "Débranche le câble de maintenance, redémarre le robot normalement, puis "
            "reviens ici. L'application vérifie ADB et TWRP ; elle ne se contente pas "
            "d'une case cochée."
        )
        self.explain.setWordWrap(True)
        self.add_widget(self.explain)
        self.mcc_check = QCheckBox("Le robot a redémarré normalement sur MCC.")
        self.mcc_check.stateChanged.connect(self.refresh)
        self.add_widget(self.mcc_check)
        self.persist_check = QCheckBox(
            "J'ai redémarré le robot deux fois et ADB répond encore."
        )
        self.persist_check.setEnabled(False)
        self.persist_check.stateChanged.connect(self.refresh)
        self.add_widget(self.persist_check)
        self.report_view = QTextBrowser()
        self.report_view.setVisible(False)
        self.add_widget(self.report_view)
        self.set_help(
            "Si MCC ne démarre pas, restaure le démarrage avec SP Flash Tool. "
            "Si ADB ne répond pas, ne déclare pas le déblocage réussi."
        )
        self.set_technical(TECH_VERIFY)
        self.set_primary_action(self._primary)
        self.set_primary("Vérifier ADB", False)

    def on_enter(self) -> None:
        state = self.window.state
        if state.completed:
            self.mcc_check.setChecked(True)
            self.report_view.setPlainText(self.window.report_text())
            self.report_view.setVisible(True)
            self.set_status("Déblocage terminé. TWRP et ADB sont disponibles.")
            self.set_primary("Terminé", False)
            return
        if state.adb_verified and not state.twrp_recovery_verified:
            self.mcc_check.setChecked(True)
            self.persist_check.setEnabled(True)
            self.set_status("ADB fonctionne. Confirme les deux redémarrages, puis vérifie TWRP.")
            self.set_primary("Vérifier TWRP", self.persist_check.isChecked())
            return
        self.set_primary("Vérifier ADB", self.mcc_check.isChecked())

    def refresh(self) -> None:
        if self.window.state.completed:
            return
        if self.window.state.adb_verified and not self.window.state.twrp_recovery_verified:
            self.set_primary("Vérifier TWRP", self.persist_check.isChecked())
        else:
            self.set_primary("Vérifier ADB", self.mcc_check.isChecked())

    def _primary(self) -> None:
        state = self.window.state
        if state.completed:
            return
        if not state.adb_verified:
            if not self.mcc_check.isChecked():
                self.set_status("Confirme que MCC a démarré.", error=True)
                return
            self.set_status("Vérification d'ADB…")
            self.window.run_async(self._verify_adb, self._adb_result)
            return
        if not state.twrp_recovery_verified:
            self.set_status("Redémarrage en mode maintenance et vérification de TWRP…")
            self.window.run_async(self.window.reboot_to_twrp, self._twrp_result)
            return

    async def _verify_adb(self):
        return await self.window.adb_check()

    def _adb_result(self, result) -> None:
        self.window.set_busy(False)
        if isinstance(result, Err):
            self.set_status(f"ADB ne répond pas : {result.message}", error=True)
            self.set_primary("Réessayer", True)
            return
        session = self.window.session
        if session is None:
            self.set_status("La session n'est pas prête.", error=True)
            return
        if isinstance(session.record_rebooted_on_mcc(mcc_started=True), Err):
            self.set_status("Impossible d'enregistrer le démarrage MCC.", error=True)
            return
        recorded = session.record_adb_verified(result.value)
        if isinstance(recorded, Err):
            self.set_status(recorded.message, error=True)
            return
        self.window.state.mcc_started = True
        self.window.state.adb_verified = True
        self.persist_check.setEnabled(True)
        self.set_status("ADB fonctionne. Confirme les deux redémarrages, puis vérifie TWRP.")
        self.set_primary("Vérifier TWRP", False)

    def _twrp_result(self, result) -> None:
        self.window.set_busy(False)
        if isinstance(result, Err):
            self.set_status(f"TWRP n'est pas accessible : {result.message}", error=True)
            self.set_primary("Réessayer", True)
            return
        self.window.state.twrp_recovery_verified = True
        session = self.window.session
        if session is None:
            self.set_status("La session n'est pas prête.", error=True)
            return
        persisted = session.record_persistence(2)
        if isinstance(persisted, Err):
            self.set_status(persisted.message, error=True)
            return
        completed = session.complete()
        if isinstance(completed, Err):
            self.set_status(completed.message, error=True)
            return
        self.window.state.completed = True
        self.report_view.setPlainText(self.window.report_text())
        self.report_view.setVisible(True)
        self.set_status("Déblocage terminé. MCC démarre, ADB répond et TWRP est installé.")
        self.set_primary("Terminé", False)


PAGES = [
    StartPage,
    ConnectPage,
    BackupPage,
    TwrpPage,
    AdbPage,
    RestorePage,
    VerifyPage,
]
