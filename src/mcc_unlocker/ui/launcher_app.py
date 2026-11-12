"""Single-window launcher for the guided unlock application."""

from __future__ import annotations

import sys
from typing import Optional

try:  # pragma: no cover - optional PyQt6
    from PyQt6.QtWidgets import QApplication

    from .unlock_app import UnlockWindow

    QT_AVAILABLE = True
except Exception:  # noqa: BLE001
    QT_AVAILABLE = False
    QApplication = None  # type: ignore[assignment]
    UnlockWindow = None  # type: ignore[assignment,misc]


def main(argv: Optional[list[str]] = None) -> int:
    if not QT_AVAILABLE:
        print("PyQt6 est requis pour l'interface graphique.", file=sys.stderr)
        return 2
    app = QApplication(argv if argv is not None else sys.argv)
    window = UnlockWindow()
    window.show()
    return app.exec()


__all__ = ["QT_AVAILABLE", "main"]
