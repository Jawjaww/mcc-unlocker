"""Reusable wizard widgets with plain-language layout."""

from __future__ import annotations

from typing import Callable, Optional

try:  # pragma: no cover - optional PyQt6
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QLabel,
        QPushButton,
        QTextBrowser,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except Exception:  # noqa: BLE001
    QT_AVAILABLE = False
    QWidget = object  # type: ignore[assignment,misc]


if QT_AVAILABLE:  # pragma: no cover - Qt rendering

    class TechnicalDetails(QWidget):
        def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.toggle = QToolButton()
            self.toggle.setText("Détails techniques")
            self.toggle.setCheckable(True)
            self.toggle.setChecked(False)
            self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.toggle.setArrowType(Qt.ArrowType.RightArrow)
            self.content = QTextBrowser()
            self.content.setOpenExternalLinks(True)
            self.content.setVisible(False)
            self.content.setMaximumHeight(180)
            layout.addWidget(self.toggle)
            layout.addWidget(self.content)
            self.toggle.toggled.connect(self._toggled)
            self.set_text(text)

        def _toggled(self, checked: bool) -> None:
            self.content.setVisible(checked)
            self.toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        def set_text(self, text: str) -> None:
            self.content.setPlainText(text)
            self.toggle.setVisible(bool(text))
            self.content.setVisible(bool(text) and self.toggle.isChecked())

    class HelpBox(QWidget):
        def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.toggle = QToolButton()
            self.toggle.setText("Si ça ne marche pas")
            self.toggle.setCheckable(True)
            self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.toggle.setArrowType(Qt.ArrowType.RightArrow)
            self.content = QLabel()
            self.content.setWordWrap(True)
            self.content.setVisible(False)
            layout.addWidget(self.toggle)
            layout.addWidget(self.content)
            self.toggle.toggled.connect(self._toggled)
            self.set_text(text)

        def _toggled(self, checked: bool) -> None:
            self.content.setVisible(checked)
            self.toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        def set_text(self, text: str) -> None:
            self.content.setText(text)
            self.content.setVisible(self.toggle.isChecked())

    class StepPage(QWidget):
        step_id: str = ""
        title: str = ""

        def __init__(self, window, step_id: str, title: str, subtitle: str) -> None:
            super().__init__()
            self.window = window
            self.step_id = step_id
            self._primary_callback: Optional[Callable[[], None]] = None
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(28, 24, 28, 16)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("stepTitle")
            self.title_label.setWordWrap(True)
            self.layout.addWidget(self.title_label)
            self.subtitle = QLabel(subtitle)
            self.subtitle.setObjectName("stepSubtitle")
            self.subtitle.setWordWrap(True)
            self.layout.addWidget(self.subtitle)
            self.body = QVBoxLayout()
            self.layout.addLayout(self.body, 1)
            self.status = QLabel("")
            self.status.setObjectName("stepStatus")
            self.status.setWordWrap(True)
            self.layout.addWidget(self.status)
            self.technical = TechnicalDetails()
            self.layout.addWidget(self.technical)
            self.help = HelpBox()
            self.layout.addWidget(self.help)
            self.primary = QPushButton("Continuer")
            self.primary.setObjectName("primaryAction")
            self.primary.clicked.connect(self.on_primary)
            self.layout.addWidget(self.primary)

        def set_technical(self, text: str) -> None:
            self.technical.set_text(text)

        def set_help(self, text: str) -> None:
            self.help.set_text(text)

        def set_status(self, text: str, *, error: bool = False) -> None:
            self.status.setText(text)
            self.status.setStyleSheet("color: #b00020;" if error else "color: #126b2f;")

        def set_primary(self, text: str, enabled: bool = True) -> None:
            self.primary.setText(text)
            self.primary.setEnabled(enabled and not self.window.busy)

        def on_primary(self) -> None:
            if self._primary_callback is not None:
                self._primary_callback()

        def set_primary_action(self, callback: Callable[[], None]) -> None:
            self._primary_callback = callback

        def on_enter(self) -> None:
            pass

        def can_leave(self) -> bool:
            return True

        def add_widget(self, widget: QWidget) -> None:
            self.body.addWidget(widget)

        def add_layout(self, layout) -> None:  # noqa: ANN001
            self.body.addLayout(layout)
