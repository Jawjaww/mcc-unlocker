"""Seven-step guided unlock window.

One primary action per page. No write occurs without a separate explicit
confirmation, and TWRP is treated as the essential maintenance environment.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from ..core.errors import ErrorCode
from ..core.result import Err, Ok
from ..hardware.adb_adapter import AdbAdapter
from ..unlock import AdbTwrpTransport, GuidedUnlockSession, TwrpAdb, UnlockProfile
from ..utils.adb import list_adb_devices, resolve_adb_path
from ..utils.filesystem import ensure_dir
from .wizard.state import STEP_ORDER, WizardState

try:  # pragma: no cover - optional PyQt6
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    from .wizard.steps import PAGES

    QT_AVAILABLE = True
except Exception:  # noqa: BLE001
    QT_AVAILABLE = False
    QApplication = None  # type: ignore[assignment]


def _mask_serial(serial: str) -> str:
    return serial if len(serial) < 10 else f"{serial[:3]}…{serial[-4:]}"


if QT_AVAILABLE:  # pragma: no cover - Qt rendering

    class AsyncWorker(QThread):
        done = pyqtSignal(object)

        def __init__(self, factory: Callable[[], object]):
            super().__init__()
            self._factory = factory

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

        def __init__(self, provider: Callable[[str], list[tuple[str, str]]], path: str):
            super().__init__()
            self._provider = provider
            self._path = path

        def run(self) -> None:
            try:
                self.done.emit(self._provider(self._path))
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
            adb_check: Callable[[], object] | None = None,
        ) -> None:
            super().__init__()
            self.setWindowTitle("MCC Unlocker — déblocage guidé")
            self.resize(900, 720)
            self.state = WizardState()
            self.session: GuidedUnlockSession | None = None
            self.session_factory = session_factory or self._default_session_factory
            self.device_provider = device_provider or (lambda adb: list_adb_devices(adb))
            self.adb_resolver = adb_resolver or resolve_adb_path
            self.out_root = Path(out_root).expanduser() if out_root else Path.home() / ".mcc-unlocker" / "unlock"
            self.work_root = ensure_dir(self.out_root)
            self._confirm_patch = confirm_patch or self._ask_patch_confirmation
            self._adb_check = adb_check or self._default_adb_check
            self.busy = False
            self._workers: list[QThread] = []
            self.pages: dict[str, object] = {}
            self._index = 0
            self._build_ui()
            self._show_step(0)

        # ------------------------------------------------------------- UI
        def _build_ui(self) -> None:
            central = QWidget()
            layout = QVBoxLayout(central)
            self.title = QLabel("MCC Unlocker")
            self.title.setObjectName("appTitle")
            layout.addWidget(self.title)
            self.step_label = QLabel("")
            self.step_label.setObjectName("stepLabel")
            layout.addWidget(self.step_label)
            self.progress = QProgressBar()
            self.progress.setRange(0, len(STEP_ORDER))
            self.progress.setTextVisible(False)
            layout.addWidget(self.progress)
            self.stack = QStackedWidget()
            layout.addWidget(self.stack, 1)
            for page_class in PAGES:
                page = page_class(self)
                self.pages[page.step_id] = page
                self.stack.addWidget(page)
            bottom = QHBoxLayout()
            self.back_button = QPushButton("Retour")
            self.back_button.clicked.connect(self.go_back)
            bottom.addWidget(self.back_button)
            bottom.addStretch(1)
            layout.addLayout(bottom)
            self.setCentralWidget(central)
            self.setStyleSheet(
                """
                QLabel#appTitle { font-size: 26px; font-weight: 700; }
                QLabel#stepLabel { font-size: 13px; color: #555; }
                QLabel#stepTitle { font-size: 22px; font-weight: 650; }
                QLabel#stepSubtitle { font-size: 14px; color: #333; }
                QLabel#stepStatus { font-size: 13px; }
                QPushButton#primaryAction { padding: 12px 18px; font-size: 15px; font-weight: 600; }
                QTextBrowser { font-size: 12px; }
                """
            )
            self._apply_busy()

        def _show_step(self, index: int) -> None:
            self._index = max(0, min(index, len(STEP_ORDER) - 1))
            page = self._current()
            self.stack.setCurrentWidget(page)
            self.step_label.setText(f"Étape {self._index + 1} sur {len(STEP_ORDER)}")
            self.progress.setValue(self._index + 1)
            self.back_button.setEnabled(self._index > 0 and not self.busy)
            page.on_enter()

        def _current(self):
            return self.pages[STEP_ORDER[self._index].value]

        def go_next(self) -> None:
            page = self._current()
            if not page.can_leave():
                page.set_status("Termine cette étape avant de continuer.", error=True)
                return
            if self._index >= len(STEP_ORDER) - 1:
                return
            self._show_step(self._index + 1)

        def go_back(self) -> None:
            if self._index > 0:
                self._show_step(self._index - 1)

        def set_busy(self, busy: bool) -> None:
            self.busy = busy
            self._apply_busy()

        def _apply_busy(self) -> None:
            self.back_button.setEnabled(self._index > 0 and not self.busy)
            if self.busy and hasattr(self, "pages") and self.pages:
                self._current().primary.setEnabled(False)

        # -------------------------------------------------------- services
        def adb_available(self) -> bool:
            path = self.adb_resolver()
            if path and path != "adb":
                return Path(path).is_file()
            return shutil.which("adb") is not None

        def mask_serial(self, serial: str) -> str:
            return _mask_serial(serial)

        def _default_session_factory(self, serial: str, work_dir: Path) -> GuidedUnlockSession:
            adb = AdbAdapter(self.adb_resolver() or "adb")
            twrp = TwrpAdb(AdbTwrpTransport(adb, serial), serial)
            return GuidedUnlockSession(UnlockProfile.reference(), work_dir, twrp)

        def _ask_patch_confirmation(self) -> bool:
            answer = QMessageBox.question(
                self,
                "Confirmer la modification",
                "Nous allons sauvegarder les réglages Android, puis autoriser ADB.\n\n"
                "Si tu refuses, le robot n'est pas modifié. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer is QMessageBox.StandardButton.Yes

        def confirm_patch(self) -> bool:
            return self._confirm_patch()

        async def _default_adb_check(self):
            adb = AdbAdapter(self.adb_resolver() or "adb")
            version = await adb.version()
            if isinstance(version, Err):
                return version
            targets = await adb.list_targets()
            if isinstance(targets, Err):
                return targets
            match = [
                target
                for target in targets.value
                if target.is_authorized and (not self.state.serial or target.serial == self.state.serial)
            ]
            if not match:
                return Err(
                    ErrorCode.ERR_ADB_NOT_AVAILABLE,
                    details={"reason": "robot sélectionné introuvable après redémarrage"},
                )
            return Ok(version.value)

        async def adb_check(self):
            return await self._adb_check()

        async def reboot_to_twrp(self):
            session = self.session
            if session is None:
                return Err(ErrorCode.ERR_PRECONDITION_NOT_MET, details={"reason": "session absente"})
            transport = session.twrp.transport
            command = await transport.shell(session.twrp.serial, "reboot recovery")
            if isinstance(command, Err):
                return command
            return await session.twrp.wait_for_twrp(120)

        def report_text(self) -> str:
            if self.session is None:
                return "Aucune session."
            return self.session.workflow.report.to_markdown()

        # ---------------------------------------------------------- workers
        def run_async(self, factory: Callable[[], object], callback: Callable[[object], None]) -> None:
            if self.busy:
                return
            self.set_busy(True)
            worker = AsyncWorker(factory)
            worker.done.connect(lambda result: self._finish_async(worker, callback, result))
            self._workers.append(worker)
            worker.start()

        def _finish_async(self, worker: QThread, callback: Callable[[object], None], result: object) -> None:
            self.set_busy(False)
            try:
                callback(result)
            finally:
                if worker in self._workers:
                    self._workers.remove(worker)
                worker.deleteLater()

        def run_devices(self, path: str, callback: Callable[[object], None]) -> None:
            if self.busy:
                return
            self.set_busy(True)
            worker = DevicesWorker(self.device_provider, path)
            worker.done.connect(lambda result: self._finish_devices(worker, callback, result))
            self._workers.append(worker)
            worker.start()

        def _finish_devices(self, worker: QThread, callback: Callable[[object], None], result: object) -> None:
            self.set_busy(False)
            try:
                callback(result)
            finally:
                if worker in self._workers:
                    self._workers.remove(worker)
                worker.deleteLater()

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
        print("PyQt6 est requis pour l'interface graphique.", file=sys.stderr)
        return 2
    app = QApplication(argv if argv is not None else sys.argv)
    window = UnlockWindow()
    window.show()
    return app.exec()


__all__ = ["QT_AVAILABLE", "UnlockWindow", "main"]
