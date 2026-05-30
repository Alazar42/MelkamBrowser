from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .browser_view import BrowserView
from .icon_manager import get_icon_manager
from .favicon_manager import FaviconManager


HOME_URL = "https://www.google.com"


DEMO_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {
    margin: 0;
    padding: 0;
    background: #202124;
    color: #E8EAED;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 16px;
    line-height: 1.6;
}
body {
    padding: 32px;
    max-width: 800px;
    margin: 0 auto;
}
h1 {
    color: #8AB4F8;
    margin-top: 0;
    font-size: 32px;
    font-weight: 300;
}
p {
    color: #BDC1C6;
    font-size: 14px;
}
button {
    background: #8AB4F8;
    color: #0D1117;
    border: none;
    padding: 10px 24px;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
}
button:hover {
    background: #AECBFA;
}
</style>
</head>
<body>
<h1 id="title">Melkam Browser</h1>
<button id="btn">Click Me</button>
<p>Python executes directly inside the browser runtime.</p>
<script type="text/python">
title = document.query("#title")
button = document.query("#btn")

def clicked(event):
    title.text = "Python Is Native"

button.on("click", clicked)
</script>
</body>
</html>
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Melkam Browser")
        self.resize(1280, 840)
        self.setUnifiedTitleAndToolBarOnMac(False)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.currentChanged.connect(self._sync_current_tab)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 0;
                background: #202124;
            }
            QTabBar {
                background: #202124;
                padding: 8px 10px 0 10px;
            }
            QTabBar::tab {
                background: #292A2D;
                color: #E8EAED;
                padding: 8px 16px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                margin-right: 6px;
                min-width: 130px;
                border: none;
            }
            QTabBar::tab:selected {
                background: #3C4043;
                color: #E8EAED;
                border: 1px solid #5F6368;
                border-bottom: 2px solid #8AB4F8;
            }
            QTabBar::tab:hover:!selected {
                background: #3C4043;
            }
            QTabBar::close-button {
                image: none;
                margin-left: 8px;
            }
            QTabBar::close-button:hover {
                background: #5F6368;
                border-radius: 4px;
            }
            """
        )

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Enter URL or HTML source")
        self.address_bar.returnPressed.connect(self._navigate_current)
        self.address_bar.setObjectName("AddressBar")
        self.address_bar.setMinimumHeight(36)

        self.status_label = QLabel("Ready")
        self.status_label.setMinimumWidth(160)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.status_label.setObjectName("StatusLabel")

        self.icon_manager = get_icon_manager(theme="dark")
        self.favicon_manager = FaviconManager(storage_root=Path.home() / ".melkam_browser")

        self.back_button = QToolButton()
        self.back_button.setIcon(self.icon_manager.icon("back", 18))
        self.back_button.setIconSize(self.icon_manager.icon("back", 18).availableSizes()[0] if self.icon_manager.icon("back", 18).availableSizes() else self.back_button.iconSize())
        self.back_button.setObjectName("NavButton")
        self.back_button.clicked.connect(lambda: self.current_view().back() if hasattr(self.current_view(), "back") else None)
        self.back_button.setFixedHeight(32)

        self.forward_button = QToolButton()
        self.forward_button.setIcon(self.icon_manager.icon("forward", 18))
        self.forward_button.setIconSize(self.icon_manager.icon("forward", 18).availableSizes()[0] if self.icon_manager.icon("forward", 18).availableSizes() else self.forward_button.iconSize())
        self.forward_button.setObjectName("NavButton")
        self.forward_button.clicked.connect(lambda: self.current_view().forward() if hasattr(self.current_view(), "forward") else None)
        self.forward_button.setFixedHeight(32)

        self.reload_button = QToolButton()
        self.reload_button.setIcon(self.icon_manager.icon("reload", 18))
        self.reload_button.setIconSize(self.icon_manager.icon("reload", 18).availableSizes()[0] if self.icon_manager.icon("reload", 18).availableSizes() else self.reload_button.iconSize())
        self.reload_button.setObjectName("NavButton")
        self.reload_button.clicked.connect(lambda: self.current_view().reload())
        self.reload_button.setFixedHeight(32)

        self.home_button = QPushButton()
        self.home_button.setIcon(self.icon_manager.icon("home", 18))
        self.home_button.setIconSize(self.home_button.iconSize().expandedTo(self.home_button.sizeHint()))
        self.home_button.setObjectName("PrimaryButton")
        self.home_button.clicked.connect(self.load_home)
        self.home_button.setFixedHeight(32)

        self.go_button = QPushButton()
        self.go_button.setIcon(self.icon_manager.icon("search", 18))
        self.go_button.setIconSize(self.go_button.iconSize().expandedTo(self.go_button.sizeHint()))
        self.go_button.setObjectName("PrimaryButton")
        self.go_button.clicked.connect(self._navigate_current)
        self.go_button.setFixedHeight(32)

        self.new_tab_button = QToolButton()
        self.new_tab_button.setIcon(self.icon_manager.icon("new_tab", 16))
        self.new_tab_button.setIconSize(self.new_tab_button.iconSize().expandedTo(self.new_tab_button.sizeHint()))
        self.new_tab_button.setObjectName("NewTabButton")
        self.new_tab_button.clicked.connect(self.new_tab_action)
        self.new_tab_button.setToolTip("New tab")
        self.new_tab_button.setFixedSize(28, 28)

        self.open_file_button = QToolButton()
        self.open_file_button.setIcon(self.icon_manager.icon("menu", 16))
        self.open_file_button.setIconSize(self.open_file_button.iconSize().expandedTo(self.open_file_button.sizeHint()))
        self.open_file_button.setObjectName("NavButton")
        self.open_file_button.clicked.connect(self.open_file)
        self.open_file_button.setToolTip("Open local file")
        self.open_file_button.setFixedHeight(32)

        self.tabs.setCornerWidget(self.new_tab_button, Qt.Corner.TopRightCorner)

        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setDocumentMode(True)
        self.inspector_tabs.setTabsClosable(False)
        self.inspector_tabs.setMaximumHeight(280)
        self.inspector_tabs.hide()

        self.inspector_view = QWebEngineView()
        self.inspector_tabs.addTab(self.inspector_view, "Inspector")

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)
        top_layout.addWidget(self.back_button)
        top_layout.addWidget(self.forward_button)
        top_layout.addWidget(self.reload_button)
        top_layout.addWidget(self.home_button)
        top_layout.addWidget(self.open_file_button)
        top_layout.addWidget(self.address_bar, 1)
        top_layout.addWidget(self.go_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top_bar)
        layout.addWidget(self.tabs)
        layout.addWidget(self.inspector_tabs)
        layout.addWidget(self.status_label)
        self.setCentralWidget(container)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #202124;
            }
            QWidget#TopBar {
                background: #202124;
                border-bottom: 1px solid #3C4043;
            }
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 12px;
                color: #E8EAED;
            }
            QWidget#AddressBar {
                background: #292A2D;
                color: #E8EAED;
                border: 1px solid #3C4043;
                border-radius: 20px;
                padding: 8px 16px;
                selection-background-color: #5F6368;
                selection-color: #E8EAED;
            }
            QWidget#AddressBar:focus {
                border: 1px solid #8AB4F8;
                background: #292A2D;
            }
            QToolButton#NavButton {
                background: transparent;
                color: #E8EAED;
                border: 1px solid transparent;
                border-radius: 16px;
                padding: 6px 10px;
                min-width: 34px;
                font-size: 13px;
                font-weight: 600;
            }
            QToolButton#NavButton:hover {
                background: #3C4043;
                border: 1px solid #5F6368;
            }
            QToolButton#NavButton:pressed {
                background: #5F6368;
            }
            QToolButton#NewTabButton {
                background: transparent;
                color: #E8EAED;
                border: 1px solid transparent;
                border-radius: 16px;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: 600;
            }
            QToolButton#NewTabButton:hover {
                background: #3C4043;
                border: 1px solid #5F6368;
            }
            QToolButton#NewTabButton:pressed {
                background: #5F6368;
            }
            QPushButton#PrimaryButton {
                background: #3C4043;
                color: #E8EAED;
                border: 1px solid #5F6368;
                border-radius: 16px;
                padding: 7px 14px;
                font-weight: 500;
            }
            QPushButton#PrimaryButton:hover {
                background: #5F6368;
                border: 1px solid #80868B;
            }
            QPushButton#PrimaryButton:pressed {
                background: #8AB4F8;
                color: #0D1117;
            }
            QLabel#StatusLabel {
                background: #292A2D;
                color: #BDC1C6;
                padding: 8px 12px;
                border-top: 1px solid #3C4043;
            }
            QFrame {
                border: 0;
            }
            """
        )

        self._install_shortcuts()
        self.new_tab(HOME_URL, "Melkam Browser")

    def _install_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+L", self.address_bar.setFocus),
            ("Ctrl+T", self.new_tab_action),
            ("Ctrl+W", self.close_current_tab),
            ("Ctrl+R", self.reload_current_tab),
            ("F5", self.reload_current_tab),
            ("Alt+Left", self.go_back),
            ("Alt+Right", self.go_forward),
            ("Ctrl+O", self.open_file),
            ("Alt+Home", self.load_home),
            ("F12", self.toggle_inspector),
            ("Ctrl+Shift+I", self.toggle_inspector),
        ]
        for sequence, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)

    def new_tab_action(self) -> None:
        self.new_tab(HOME_URL, "New Tab")

    def new_tab(self, target: str, title: str = "New Tab") -> BrowserView:
        view = BrowserView()
        view.title_changed.connect(lambda value, tab=view: self._rename_tab(tab, value))
        view.url_changed.connect(self.address_bar.setText)
        view.status_changed.connect(self.status_label.setText)
        index = self.tabs.addTab(view, title)
        # default tab icon until favicon is available
        self.tabs.setTabIcon(index, self.icon_manager.icon("browser", 16))
        # connect favicon updates
        def _on_url_changed(url: str, idx=index):
            self.favicon_manager.fetch(url)

        view.url_changed.connect(_on_url_changed)
        def _apply_favicon(host: str, path: str, idx=index):
            from PySide6.QtGui import QIcon
            if path:
                self.tabs.setTabIcon(idx, QIcon(path))
        self.favicon_manager.favicon_ready.connect(_apply_favicon)
        self.tabs.setCurrentIndex(index)
        self._attach_inspector_to_current()
        view.navigate(target)
        return view

    def current_view(self) -> BrowserView:
        widget = self.tabs.currentWidget()
        assert isinstance(widget, BrowserView)
        return widget

    def _navigate_current(self) -> None:
        self.current_view().navigate(self.address_bar.text())

    def load_home(self) -> None:
        self.current_view().navigate(HOME_URL)

    def reload_current_tab(self) -> None:
        self.current_view().reload()

    def close_current_tab(self) -> None:
        self._close_tab(self.tabs.currentIndex())

    def go_back(self) -> None:
        view = self.current_view()
        if hasattr(view, "back"):
            view.back()

    def go_forward(self) -> None:
        view = self.current_view()
        if hasattr(view, "forward"):
            view.forward()

    def _close_tab(self, index: int) -> None:
        if self.tabs.count() <= 1:
            return
        widget = self.tabs.widget(index)
        if isinstance(widget, BrowserView):
            if widget.page_model and hasattr(widget.page_model, "python_runtime"):
                widget.page_model.python_runtime.cleanup()
        self.tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()

    def _sync_current_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, BrowserView):
            self.address_bar.setText(widget.current_url)

    def _on_tab_changed(self, index: int) -> None:
        self._sync_current_tab(index)
        self._attach_inspector_to_current()

    def _attach_inspector_to_current(self) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, BrowserView):
            widget.attach_devtools(self.inspector_view)

    def toggle_inspector(self) -> None:
        showing = self.inspector_tabs.isVisible()
        self.inspector_tabs.setVisible(not showing)
        if not showing:
            self._attach_inspector_to_current()

    def open_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            str(Path.home()),
            "Web Files (*.html *.htm *.txt *.md);;All Files (*.*)",
        )
        if selected:
            self.current_view().navigate(selected)

    def _rename_tab(self, view: BrowserView, title: str) -> None:
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setTabText(index, title or "Tab")