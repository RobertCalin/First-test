"""Entry point: sets per-monitor DPI awareness (must happen before QApplication is
created), installs a global exception hook so a startup failure shows a dialog instead
of the process dying silently, and runs the overlay.
"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from .native import set_per_monitor_dpi_aware
from .overlay_window import OverlayWindow


def _install_exception_hook(app: QApplication) -> None:
    # An overlay app that fails silently is worse than useless -- with no console window
    # and nothing else visible, a swallowed startup exception would otherwise look
    # identical to "it's running but invisible."
    def hook(exc_type, exc_value, exc_tb) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        QMessageBox.critical(
            None,
            "AgentOverlay - Unhandled Exception",
            f"AgentOverlay crashed:\n\n{details}",
        )
        app.quit()

    sys.excepthook = hook


def main() -> None:
    set_per_monitor_dpi_aware()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    _install_exception_hook(app)

    window = OverlayWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
