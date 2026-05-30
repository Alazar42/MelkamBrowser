from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .gui.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Melkam Browser")
    app.setOrganizationName("Melkam")

    window = MainWindow()
    window.showMaximized()

    return app.exec()