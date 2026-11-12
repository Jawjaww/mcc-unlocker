"""Guided unlock desktop UI (SP Flash Tool + TWRP).

The UI never drives SP Flash Tool or TWRP GUI. It validates the user's files,
waits for TWRP over USB ADB, applies the build.prop patch with explicit
confirmation, guides the two final TWRP image flashes, and records functional
evidence.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..core.errors import ErrorCode
from ..core.result import Err, Ok
from ..hardware.adb_adapter import AdbAdapter
from ..utils.adb import list_adb_devices, resolve_adb_path
from ..unlock import (
    AdbTwrpTransport,
    GuidedUnlockSession,
    SpFlashGuide,
    TwrpAdb,
    UnlockProfile,
    load_community_assets,
)
from ..utils.filesystem import ensure_dir
from ..utils.paths import project_root

try:  # pragma: no cover - optional PyQt6
    from PyQt6.QtCore import QThread, QUrl, pyqtSignal
    from PyQt6.QtGui import QDesktopServices, QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QStackedWidget,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except Exception:  # noqa: BLE001
    QT_AVAILABLE = False
    QApplication = None  # type: ignore[assignment]


def _mask_serial(serial: str) -> str:
    return serial if len(serial) < 10 else f"{serial[:3]}…{serial[-4:]}"


if QT_AVAILABLE:  # pragma: no cover - Qt rendering

    class AsyncWorker(QThread):
        done = pyqtSignal(object)

        def __init__(self, coroutine_factory: Callable[[], object]):
            super().__init__()
            self._factory = coroutine_factory

        def run(self) -> None:
            try:
                result = asyncio.run(self._factory())
            except Exception as exc:  # noqa: BLE001
                result = Err(
                    ErrorCode.ERR_INTERNAL,
                    details={"error": f"{type(exc).__name__}: {exc}"},
                )
            self.done.emit(result)

    class DevicesWorker(QThread):
        done = pyqtSignal(object)

        def __init__(self, provider: Callable[[str], list[tuple[str, str]]], adb_path: str):
            super().__init__()
            self._provider = provider
            self._adb_path = adb_path

        def run(self) -> None:
            try:
                self.done.emit(self._provider(self._adb_path))
            except Exception as exc:  # noqa: BLE001
                self.done.emit(Err(ErrorCode.ERR_ADB_NOT_AVAILABLE, details={"error": str(exc)}))

    class UnlockWindow(QMainWindow):
        def __init__(
            self,
            *,
            session_factory: Callable[[str, Path], GuidedUnlockSession] | None = None,
            device_provider: Callable[[str], list[tuple[str, str]]] | None = None,
            adb_resolver: Callable[[], str] | None = None,
            out_root: Path | str | None = None,
            confirm_patch: Callable[[], bool] | None = None,
        ) -> None:
            super().__init__()
            self.setWindowTitle("MCC Unlocker — déblocage guidé")
            self.resize(980, 760)
            self.session_factory = session_factory or self._default_session_factory
            self.device_provider = device_provider or (lambda adb: list_adb_devices(adb))
            self.adb_resolver = adb_resolver or resolve_adb_path
            self.out_root = Path(out_root).expanduser() if out_root else Path.home() / ".mcc-unlocker" / "unlock"
            self.session: GuidedUnlockSession | None = None
            self._serial = ""
            self._workers: list[QThread] = []
            self._busy = False
            self._adb_path = ""
            self._confirm_patch = confirm_patch or self._ask_patch_confirmation
            self._build_ui()
            self._prefill_community_assets()

        def _prefill_community_assets(self) -> None:
            assets = load_community_assets()
            if not assets.is_ok:
                return
            self.scatter_edit.setText(str(assets.value.scatter))
            self.twrp_edit.setText(str(assets.value.recovery_img))
            self.twrp_sha_edit.setText(assets.value.recovery_sha256)
            self.intro_status.setText(
                "Assets communautaires détectés. Vérifie qu'ils correspondent à ton firmware ; "
                "le M0 reste obligatoire."
            )
            self._refresh_start()

        # ------------------------------------------------------------ UI
        def _build_ui(self) -> None:
            central = QWidget()
            layout = QVBoxLayout(central)
            self.stack = QStackedWidget()
            layout.addWidget(self.stack, 1)
            self.stack.addWidget(self._build_intro())
            self.stack.addWidget(self._build_session())
            self.stack.addWidget(self._build_done())
            self.setCentralWidget(central)

        def _build_intro(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel("Déblocage guidé MCC — SP Flash Tool + TWRP")
            title.setFont(QFont("", 19, QFont.Weight.Bold))
            layout.addWidget(title)

            warning = QLabel(
                "<b>Opération sensible.</b> Cette étape modifie la partition de "
                "démarrage et <code>/system</code> du robot. Un brick reste possible. "
                "Utilise uniquement le port droit « Android USB » ; le port gauche "
                "peut endommager l'appareil.<br><br>"
                "La procédure n'est <b>pas validée</b> sur le firmware 4921 tant que "
                "le M0 n'a pas été exécuté."
            )
            warning.setWordWrap(True)
            layout.addWidget(warning)

            self.owner_check = QCheckBox("Je possède ce robot et j'accepte le risque.")
            self.port_check = QCheckBox("J'utilise le port droit « Android USB ».")
            self.prereq_check = QCheckBox(
                "J'ai installé SP Flash Tool et son pilote, et TWRP est déjà flashé "
                "dans boot (le robot démarre sur TWRP)."
            )
            layout.addWidget(self.owner_check)
            layout.addWidget(self.port_check)
            layout.addWidget(self.prereq_check)

            files = QGroupBox("Fichiers validés avant de commencer")
            form = QFormLayout(files)
            self.scatter_edit = QLineEdit()
            self.boot_edit = QLineEdit()
            self.twrp_edit = QLineEdit()
            self.twrp_sha_edit = QLineEdit()
            form.addRow("Scatter :", self._file_row(self.scatter_edit, "Scatter (*.txt)"))
            form.addRow("Backup boot :", self._file_row(self.boot_edit, "Image (*.img *.bin)"))
            form.addRow("Image TWRP :", self._file_row(self.twrp_edit, "Image (*.img)"))
            form.addRow("SHA-256 TWRP (optionnel) :", self.twrp_sha_edit)
            layout.addWidget(files)

            twrp_box = QGroupBox("TWRP doit déjà être démarré")
            row = QHBoxLayout(twrp_box)
            self.device_combo = QComboBox()
            self.device_combo.setMinimumWidth(320)
            self.search_twrp_button = QPushButton("Rechercher TWRP en ADB")
            self.search_twrp_button.clicked.connect(self._search_twrp)
            row.addWidget(self.device_combo, 1)
            row.addWidget(self.search_twrp_button)
            layout.addWidget(twrp_box)

            self.intro_status = QLabel("")
            self.intro_status.setWordWrap(True)
            layout.addWidget(self.intro_status)

            guide_view = QTextBrowser()
            guide_view.setPlainText(SpFlashGuide().to_markdown())
            guide_view.setMaximumHeight(230)
            layout.addWidget(guide_view)

            row = QHBoxLayout()
            self.start_button = QPushButton("Valider les fichiers et vérifier TWRP")
            self.start_button.clicked.connect(self._start)
            self.start_button.setEnabled(False)
            self.owner_check.stateChanged.connect(self._refresh_start)
            self.port_check.stateChanged.connect(self._refresh_start)
            self.prereq_check.stateChanged.connect(self._refresh_start)
            guide = QPushButton("Ouvrir le guide complet")
            guide.clicked.connect(self._open_guide)
            row.addWidget(self.start_button, 1)
            row.addWidget(guide)
            layout.addLayout(row)
            return page

        def _file_row(self, edit: QLineEdit, label: str) -> QWidget:
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            choose = QPushButton("Parcourir…")
            choose.clicked.connect(lambda: self._browse(edit, label))
            row.addWidget(edit, 1)
            row.addWidget(choose)
            return container

        def _build_session(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel("Session TWRP")
            title.setFont(QFont("", 17, QFont.Weight.Bold))
            layout.addWidget(title)
            self.session_status = QLabel("")
            self.session_status.setWordWrap(True)
            layout.addWidget(self.session_status)
            self.session_log = QPlainTextEdit()
            self.session_log.setReadOnly(True)
            layout.addWidget(self.session_log, 1)

            self.patch_button = QPushButton(
                "Sauvegarder et patcher /system (confirmation explicite requise)"
            )
            self.patch_button.clicked.connect(self._patch_system)
            self.patch_button.setEnabled(False)
            layout.addWidget(self.patch_button)

            row = QHBoxLayout()
            self.push_button = QPushButton("Pousser bootimg.bin et recovery.bin")
            self.push_button.clicked.connect(self._push_final)
            self.push_button.setEnabled(False)
            row.addWidget(self.push_button)
            layout.addLayout(row)

            flash_box = QGroupBox("Flashs finaux dans TWRP GUI")
            flash_layout = QVBoxLayout(flash_box)
            flash_layout.addWidget(
                QLabel(
                    "Dans TWRP : Install → Install Image. bootimg.bin dans boot, "
                    "puis recovery.bin dans recovery. Ne pas inverser."
                )
            )
            self.boot_flash_check = QCheckBox("bootimg.bin flashé dans boot")
            self.recovery_flash_check = QCheckBox("recovery.bin flashé dans recovery")
            flash_layout.addWidget(self.boot_flash_check)
            flash_layout.addWidget(self.recovery_flash_check)
            self.confirm_flash_button = QPushButton("Confirmer les deux flashs TWRP")
            self.confirm_flash_button.clicked.connect(self._confirm_flashes)
            self.confirm_flash_button.setEnabled(False)
            flash_layout.addWidget(self.confirm_flash_button)
            layout.addWidget(flash_box)

            verify_box = QGroupBox("Vérification fonctionnelle")
            verify_layout = QVBoxLayout(verify_box)
            self.reboot_button = QPushButton("J'ai redémarré sur MCC")
            self.reboot_button.clicked.connect(self._rebooted)
            self.reboot_button.setEnabled(False)
            self.adb_button = QPushButton("Vérifier ADB sur le robot")
            self.adb_button.clicked.connect(self._verify_adb)
            self.adb_button.setEnabled(False)
            self.persist_button = QPushButton("ADB persiste après 2 redémarrages à froid")
            self.persist_button.clicked.connect(self._persistence)
            self.persist_button.setEnabled(False)
            self.complete_button = QPushButton("Terminer et écrire le rapport")
            self.complete_button.clicked.connect(self._complete)
            self.complete_button.setEnabled(False)
            for button in (
                self.reboot_button,
                self.adb_button,
                self.persist_button,
                self.complete_button,
            ):
                verify_layout.addWidget(button)
            layout.addWidget(verify_box)
            return page

        def _build_done(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel("Session terminée")
            title.setFont(QFont("", 17, QFont.Weight.Bold))
            layout.addWidget(title)
            self.done_status = QLabel("")
            self.done_status.setWordWrap(True)
            layout.addWidget(self.done_status)
            self.report_view = QTextBrowser()
            layout.addWidget(self.report_view, 1)
            row = QHBoxLayout()
            open_folder = QPushButton("Ouvrir le dossier du rapport")
            open_folder.clicked.connect(self._open_report_folder)
            restart = QPushButton("Nouvelle session")
            restart.clicked.connect(self._restart)
            row.addWidget(open_folder)
            row.addWidget(restart)
            layout.addLayout(row)
            return page

        def _default_session_factory(self, serial: str, work_dir: Path) -> GuidedUnlockSession:
            adb = AdbAdapter(self._adb_path or "adb")
            twrp = TwrpAdb(AdbTwrpTransport(adb, serial), serial)
            return GuidedUnlockSession(UnlockProfile.reference(), work_dir, twrp)

        # ------------------------------------------------------- interaction
        def _browse(self, edit: QLineEdit, label: str) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", "", label)
            if path:
                edit.setText(path)
                if edit is self.twrp_edit:
                    self.twrp_sha_edit.clear()
                self._refresh_start()

        def _refresh_start(self) -> None:
            ready = bool(
                self.owner_check.isChecked()
                and self.port_check.isChecked()
                and self.prereq_check.isChecked()
                and self.scatter_edit.text().strip()
                and self.boot_edit.text().strip()
                and self.twrp_edit.text().strip()
                and self.device_combo.count()
            )
            self.start_button.setEnabled(ready and not self._busy)

        def _search_twrp(self) -> None:
            self._adb_path = self.adb_resolver()
            if not self._adb_path:
                self._show_error("ADB introuvable. Installe Android platform-tools.")
                return
            worker = DevicesWorker(self.device_provider, self._adb_path)
            worker.done.connect(self._devices_found)
            self._start_worker(worker)

        def _devices_found(self, result: object) -> None:
            self.device_combo.clear()
            if isinstance(result, Err):
                self.intro_status.setText(result.message)
                return
            devices = result.value if isinstance(result, Ok) else result
            if not isinstance(devices, (list, tuple)):
                devices = []
            for serial, state in devices:
                if state != "device":
                    continue
                self.device_combo.addItem(f"TWRP {_mask_serial(serial)} — {state}", serial)
            if not self.device_combo.count():
                self.intro_status.setText(
                    "Aucun appareil ADB autorisé. Démarre TWRP, branche le câble USB, "
                    "puis réessaie."
                )
            else:
                self.intro_status.setText("TWRP détecté. Vérifie les fichiers puis continue.")
            self._refresh_start()

        def _start(self) -> None:
            if self._busy:
                return
            if not (
                self.owner_check.isChecked()
                and self.port_check.isChecked()
                and self.prereq_check.isChecked()
            ):
                self._show_error(
                    "Confirme la propriété, le port droit, SP Flash Tool et le flash préalable de TWRP."
                )
                return
            serial = self.device_combo.currentData()
            if not serial:
                self._show_error("Sélectionne TWRP dans la liste ADB.")
                return
            guide = SpFlashGuide(UnlockProfile.reference())
            scatter = guide.validate_scatter(self.scatter_edit.text().strip())
            if isinstance(scatter, Err):
                self._show_error(scatter)
                return
            boot = guide.validate_boot_backup(self.boot_edit.text().strip())
            if isinstance(boot, Err):
                self._show_error(boot)
                return
            sha = self.twrp_sha_edit.text().strip() or None
            image = guide.validate_twrp(self.twrp_edit.text().strip(), expected_sha256=sha)
            if isinstance(image, Err):
                self._show_error(image)
                return
            stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            work_dir = ensure_dir(self.out_root / f"unlock-{stamp}")
            self._serial = str(serial)
            self.session = self.session_factory(str(serial), work_dir)
            for result in (
                self.session.accept_consent(),
                self.session.validate_boot_backup(self.boot_edit.text().strip()),
                self.session.validate_twrp_image(self.twrp_edit.text().strip(), expected_sha256=sha),
                self.session.record_twrp_boot_flash(),
            ):
                if isinstance(result, Err):
                    self._show_error(result)
                    return
            self.stack.setCurrentIndex(1)
            self.session_status.setText(
                "Attente de TWRP. Aucune modification de /system n'a encore été effectuée."
            )
            self._append_log("Session créée. Recherche de TWRP ; aucune écriture.")
            self._run_async(self._wait_for_twrp, self._after_twrp_ready)

        async def _wait_for_twrp(self):
            assert self.session is not None
            return await self.session.wait_for_twrp(120)

        def _after_twrp_ready(self, result: object) -> None:
            if isinstance(result, Err):
                self.session_status.setText("TWRP n'est pas accessible.")
                self._append_log(f"Erreur : {result.code.value} — {result.message}")
                self._show_error(result)
                return
            self.session_status.setText(
                "TWRP est prêt. Aucune modification n'a été faite. "
                "Le bouton de patch demande une confirmation explicite."
            )
            self._append_log(f"TWRP prêt : {result.value}. Aucune écriture effectuée.")
            self.patch_button.setEnabled(True)

        def _ask_patch_confirmation(self) -> bool:
            answer = QMessageBox.question(
                self,
                "Confirmer le patch système",
                "Cette étape va sauvegarder puis modifier /system/build.prop et "
                "supprimer recovery-from-boot.p.\n\n"
                "Le robot est sous TWRP, le backup boot est vérifié et tu acceptes "
                "cette modification. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer is QMessageBox.StandardButton.Yes

        def _patch_system(self) -> None:
            if self.session is None:
                return
            if not self._confirm_patch():
                self._append_log("Patch annulé : confirmation refusée.")
                self.session_status.setText("Patch non confirmé. Aucune écriture effectuée.")
                return
            self.patch_button.setEnabled(False)
            self._append_log("Confirmation reçue : sauvegarde et patch de /system.")
            self._run_async(self.session.patch_system, self._after_patch)

        def _after_patch(self, result: object) -> None:
            if isinstance(result, Err):
                self.session_status.setText("Patch interrompu.")
                self._append_log(f"Erreur : {result.code.value} — {result.message}")
                self._show_error(result)
                return
            self.session_status.setText(
                "Patch système vérifié. Pousse les fichiers finaux avec le bouton ci-dessous."
            )
            self._append_log("build.prop patché et vérifié. recovery-from-boot.p traité.")
            self.push_button.setEnabled(True)

        def _push_final(self) -> None:
            if self.session is None:
                return
            self.push_button.setEnabled(False)
            self._run_async(self.session.push_final_images, self._after_push)

        def _after_push(self, result: object) -> None:
            if isinstance(result, Err):
                self.push_button.setEnabled(True)
                self._show_error(result)
                return
            self._append_log("bootimg.bin et recovery.bin poussés dans /sdcard/.")
            self.session_status.setText(
                "Fais les deux Install Image dans TWRP GUI, puis coche les deux cases."
            )
            self.confirm_flash_button.setEnabled(True)

        def _confirm_flashes(self) -> None:
            if self.session is None:
                return
            result = self.session.record_final_flashes(
                boot=self.boot_flash_check.isChecked(),
                recovery=self.recovery_flash_check.isChecked(),
            )
            if isinstance(result, Err):
                self._show_error(result)
                return
            self.reboot_button.setEnabled(True)
            self.session_status.setText("Flashs confirmés. Redémarre le robot sur MCC.")
            self._append_log("Flashs TWRP finaux confirmés par l'utilisateur.")

        def _rebooted(self) -> None:
            if self.session is None:
                return
            result = self.session.record_rebooted_on_mcc(mcc_started=True)
            if isinstance(result, Err):
                self._show_error(result)
                return
            self.adb_button.setEnabled(True)
            self.session_status.setText("Redémarrage MCC confirmé. Vérifie ADB.")
            self._append_log("Démarrage MCC confirmé.")

        def _verify_adb(self) -> None:
            if self.session is None:
                return
            self.adb_button.setEnabled(False)
            self._run_async(self._adb_check, self._after_adb)

        async def _adb_check(self):
            adb = AdbAdapter(self._adb_path or self.adb_resolver() or "adb")
            version = await adb.version()
            if isinstance(version, Err):
                return version
            targets = await adb.list_targets()
            if isinstance(targets, Err):
                return targets
            authorized = [
                target
                for target in targets.value
                if target.is_authorized and (not self._serial or target.serial == self._serial)
            ]
            if not authorized:
                return Err(
                    ErrorCode.ERR_ADB_NOT_AVAILABLE,
                    details={"reason": "selected device not found after reboot"},
                )
            return Ok(version.value)

        def _after_adb(self, result: object) -> None:
            if isinstance(result, Err):
                self.adb_button.setEnabled(True)
                self._show_error(result)
                return
            assert self.session is not None
            recorded = self.session.record_adb_verified(result.value)
            if isinstance(recorded, Err):
                self._show_error(recorded)
                return
            self.persist_button.setEnabled(True)
            self.session_status.setText("ADB vérifié. Confirme deux redémarrages à froid.")
            self._append_log(f"ADB : {result.value}")

        def _persistence(self) -> None:
            if self.session is None:
                return
            result = self.session.record_persistence(2)
            if isinstance(result, Err):
                self._show_error(result)
                return
            self.complete_button.setEnabled(True)
            self.session_status.setText("Persistance confirmée. Tu peux terminer la session.")
            self._append_log("Deux redémarrages à froid confirmés.")

        def _complete(self) -> None:
            if self.session is None:
                return
            result = self.session.complete()
            if isinstance(result, Err):
                self._show_error(result)
                return
            self.done_status.setText(
                "Session terminée. Le déblocage est fonctionnellement réussi ; "
                "aucune preuve bit-à-bit des partitions finales n'est incluse."
            )
            self.report_view.setPlainText(
                self.session.workflow.report.to_markdown()
            )
            self.stack.setCurrentIndex(2)

        # ---------------------------------------------------------- helpers
        def _run_async(self, factory, callback) -> None:
            if self._busy:
                return
            worker = AsyncWorker(factory)
            worker.done.connect(callback)
            self._start_worker(worker)

        def _start_worker(self, worker: QThread) -> None:
            self._busy = True
            self.start_button.setEnabled(False)
            self.search_twrp_button.setEnabled(False)
            self._workers.append(worker)
            worker.finished.connect(lambda: self._worker_finished(worker))
            worker.start()

        def _worker_finished(self, worker: QThread) -> None:
            self._busy = False
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()
            self._refresh_start()
            self.search_twrp_button.setEnabled(True)

        def _set_error(self, result: Err) -> None:
            self._append_log(f"{result.code.value} : {result.message}")
            QMessageBox.critical(self, "Erreur", f"{result.message}\n\nCode : {result.code.value}")

        def _show_error(self, result) -> None:
            if isinstance(result, Err):
                self._set_error(result)
            else:
                self._set_error(Err(ErrorCode.ERR_INTERNAL, details={"value": str(result)}))

        def _append_log(self, message: str) -> None:
            self.session_log.appendPlainText(message)

        def _open_guide(self) -> None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(project_root() / "docs" / "unlock-v1.md"))
            )

        def _open_report_folder(self) -> None:
            if self.session is not None:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.work_dir)))

        def _restart(self) -> None:
            self.session = None
            self.stack.setCurrentIndex(0)
            self.session_log.clear()
            self.report_view.clear()
            self.patch_button.setEnabled(False)
            self.push_button.setEnabled(False)
            self.confirm_flash_button.setEnabled(False)
            self.reboot_button.setEnabled(False)
            self.adb_button.setEnabled(False)
            self.persist_button.setEnabled(False)
            self.complete_button.setEnabled(False)
            self._refresh_start()

        def closeEvent(self, event) -> None:  # noqa: N802
            if any(worker.isRunning() for worker in self._workers):
                QMessageBox.information(
                    self,
                    "Opération en cours",
                    "Attends la fin de l'opération avant de fermer.",
                )
                event.ignore()
                return
            super().closeEvent(event)


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - GUI entry
    if not QT_AVAILABLE:
        print(
            "PyQt6 est requis pour l'interface graphique.\n"
            "Installe-le avec : pip install 'mcc-unlocker[gui]'",
            file=sys.stderr,
        )
        return 2
    app = QApplication(argv if argv is not None else sys.argv)
    window = UnlockWindow()
    window.show()
    return app.exec()


__all__ = ["QT_AVAILABLE", "UnlockWindow", "main"]
