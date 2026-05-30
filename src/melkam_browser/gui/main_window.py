from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .browser_view import BrowserView
from .favicon_manager import FaviconManager


HOME_URL = "https://www.google.com"


def _shell_html() -> str:
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<style>
:root {
  --bg: #202124;
  --panel: #292a2d;
  --panel-hover: #3c4043;
  --line: #3c4043;
  --text: #e8eaed;
  --muted: #bdc1c6;
  --accent: #8ab4f8;
}
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  user-select: none;
  overflow: hidden;
  height: 100%;
}
#shell {
  border-bottom: 1px solid var(--line);
  overflow: hidden;
  height: 92px;
}
#tabstrip {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 8px 10px 0 10px;
  background: var(--bg);
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--panel);
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
  min-width: 140px;
  max-width: 240px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  color: var(--text);
  cursor: pointer;
}
.tab.active {
  background: var(--panel-hover);
  border-color: #5f6368;
  border-bottom: 2px solid var(--accent);
}
.tab .title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.tab .close {
  width: 18px;
  height: 18px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: var(--muted);
}
.tab .close:hover {
  background: #5f6368;
  color: var(--text);
}
#newTab {
  width: 28px;
  height: 28px;
  border-radius: 14px;
  border: 1px solid transparent;
  display: grid;
  place-items: center;
  color: var(--text);
  cursor: pointer;
  margin-left: 2px;
}
#newTab:hover {
  background: var(--panel-hover);
  border-color: #5f6368;
}
#toolbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-top: 1px solid #2a2d30;
}
#nav {
  display: flex;
  align-items: center;
  gap: 6px;
}
.btn {
  width: 32px;
  height: 32px;
  border-radius: 16px;
  border: 1px solid transparent;
  display: grid;
  place-items: center;
  color: var(--text);
  cursor: pointer;
}
.btn:hover {
  background: var(--panel-hover);
  border-color: #5f6368;
}
#omnibox {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  height: 34px;
  display: flex;
  align-items: center;
  padding: 0 12px;
}
#url {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-size: 13px;
}
#profile {
  width: 32px;
  height: 32px;
  border-radius: 16px;
  background: #b3d9f5;
}
</style>
</head>
<body>
  <div id=\"shell\">
    <div id=\"tabstrip\"></div>
    <div id=\"toolbar\">
      <div id=\"nav\">
        <div class=\"btn\" id=\"back\">&#8592;</div>
        <div class=\"btn\" id=\"forward\">&#8594;</div>
        <div class=\"btn\" id=\"reload\">&#8635;</div>
        <div class=\"btn\" id=\"home\">&#8962;</div>
      </div>
      <div id=\"omnibox\">
        <input id=\"url\" placeholder=\"Search Google or type a URL\" />
      </div>
      <div id=\"profile\"></div>
    </div>
  </div>

<script src=\"qrc:///qtwebchannel/qwebchannel.js\"></script>
<script>
let api = null;
let tabs = [];
let activeId = null;

function esc(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function render() {
  const strip = document.getElementById('tabstrip');
  strip.innerHTML = '';

  for (const tab of tabs) {
    const el = document.createElement('div');
    el.className = 'tab' + (tab.id === activeId ? ' active' : '');
    el.innerHTML = `<span class=\"title\">${esc(tab.title || 'Tab')}</span><span class=\"close\">&#10005;</span>`;
    el.addEventListener('click', () => api && api.activateTab(tab.id));
    el.querySelector('.close').addEventListener('click', (ev) => {
      ev.stopPropagation();
      api && api.closeTab(tab.id);
    });
    strip.appendChild(el);
  }

  const plus = document.createElement('div');
  plus.id = 'newTab';
  plus.innerHTML = '&#43;';
  plus.addEventListener('click', () => api && api.newTab());
  strip.appendChild(plus);
}

function setUrl(value) {
  document.getElementById('url').value = value || '';
}

window.shellSync = function(payloadJson) {
  const payload = JSON.parse(payloadJson);
  tabs = payload.tabs || [];
  activeId = payload.activeId || null;
  render();
  setUrl(payload.currentUrl || '');
}

window.addEventListener('DOMContentLoaded', () => {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    api = channel.objects.shellApi;

    document.getElementById('back').addEventListener('click', () => api.back());
    document.getElementById('forward').addEventListener('click', () => api.forward());
    document.getElementById('reload').addEventListener('click', () => api.reload());
    document.getElementById('home').addEventListener('click', () => api.home());

    const url = document.getElementById('url');
    url.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        api.navigate(url.value);
      }
    });

    api.requestInitialState();
  });
});
</script>
</body>
</html>
"""


class ShellBridge(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window

    @Slot()
    def requestInitialState(self) -> None:
        self.window._sync_shell()

    @Slot()
    def newTab(self) -> None:
        self.window.new_tab(HOME_URL, "New Tab")

    @Slot(str)
    def activateTab(self, tab_id: str) -> None:
        self.window._activate_tab_id(tab_id)

    @Slot(str)
    def closeTab(self, tab_id: str) -> None:
        self.window._close_tab_id(tab_id)

    @Slot(str)
    def navigate(self, target: str) -> None:
        self.window._navigate_current(target)

    @Slot()
    def back(self) -> None:
        view = self.window.current_view()
        if view is not None:
            view.back()

    @Slot()
    def forward(self) -> None:
        view = self.window.current_view()
        if view is not None:
            view.forward()

    @Slot()
    def reload(self) -> None:
        view = self.window.current_view()
        if view is not None:
            view.reload()

    @Slot()
    def home(self) -> None:
        self.window._navigate_current(HOME_URL)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Melkam Browser")
        self.resize(1280, 840)

        self.favicon_manager = FaviconManager(storage_root=Path.home() / ".melkam_browser")

        self._tab_seq = 0
        self._tab_ids: dict[int, str] = {}

        self.shell_view = QWebEngineView()
        self.shell_view.setFixedHeight(92)
        self.shell_bridge = ShellBridge(self)
        self.shell_channel = QWebChannel(self.shell_view.page())
        self.shell_channel.registerObject("shellApi", self.shell_bridge)
        self.shell_view.page().setWebChannel(self.shell_channel)
        self.shell_view.setHtml(_shell_html(), QUrl("about:blank"))

        self.page_stack = QStackedWidget()

        self.address_bar = QLineEdit()
        self.address_bar.hide()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.shell_view)
        layout.addWidget(self.page_stack, 1)
        self.setCentralWidget(container)

        self._install_shortcuts()
        self.new_tab(HOME_URL, "Melkam Browser")

    def _install_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+T", self.new_tab_action),
            ("Ctrl+W", self.close_current_tab),
            ("Ctrl+R", self.reload_current_tab),
            ("F5", self.reload_current_tab),
            ("Alt+Left", self.go_back),
            ("Alt+Right", self.go_forward),
            ("Ctrl+O", self.open_file),
            ("Alt+Home", self.load_home),
        ]
        for sequence, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)

    def _new_tab_id(self) -> str:
        self._tab_seq += 1
        return f"tab-{self._tab_seq}"

    def _tab_index_for_id(self, tab_id: str) -> int:
        for index, current_id in self._tab_ids.items():
            if current_id == tab_id:
                return index
        return -1

    def _reindex_tab_ids(self) -> None:
      ordered_ids: list[str] = []
      for index in range(self.page_stack.count()):
        widget = self.page_stack.widget(index)
        if widget is None:
          continue

        tab_id = ""
        for key, value in self._tab_ids.items():
          if self.page_stack.widget(key) is widget:
            tab_id = value
            break

        if tab_id:
          ordered_ids.append(tab_id)

      self._tab_ids = {idx: tab_id for idx, tab_id in enumerate(ordered_ids)}

    def _shell_payload(self) -> dict[str, Any]:
        tabs: list[dict[str, str]] = []
        for index in range(self.page_stack.count()):
            widget = self.page_stack.widget(index)
            if not isinstance(widget, BrowserView):
                continue
            tab_id = self._tab_ids.get(index, "")
            title = widget.title() or "Tab"
            tabs.append({"id": tab_id, "title": title})

        active_index = self.page_stack.currentIndex()
        active_id = self._tab_ids.get(active_index, "") if active_index >= 0 else ""
        current_url = ""
        current = self.current_view()
        if current is not None:
            current_url = current.current_url

        return {
            "tabs": tabs,
            "activeId": active_id,
            "currentUrl": current_url,
        }

    def _sync_shell(self) -> None:
        payload = json.dumps(self._shell_payload())
        script = f"window.shellSync && window.shellSync({json.dumps(payload)});"
        self.shell_view.page().runJavaScript(script)

    def new_tab_action(self) -> None:
        self.new_tab(HOME_URL, "New Tab")

    def new_tab(self, target: str, title: str = "New Tab") -> BrowserView:
        view = BrowserView()
        view.title_changed.connect(lambda _value: self._sync_shell())
        view.url_changed.connect(lambda _value: self._sync_shell())
        index = self.page_stack.addWidget(view)
        self._tab_ids[index] = self._new_tab_id()
        self.page_stack.setCurrentIndex(index)
        view.navigate(target)
        self._sync_shell()
        return view

    def current_view(self) -> BrowserView | None:
        widget = self.page_stack.currentWidget()
        if isinstance(widget, BrowserView):
            return widget
        return None

    def _activate_tab_id(self, tab_id: str) -> None:
        index = self._tab_index_for_id(tab_id)
        if index >= 0:
            self.page_stack.setCurrentIndex(index)
            self._sync_shell()

    def _close_tab_id(self, tab_id: str) -> None:
        index = self._tab_index_for_id(tab_id)
        if index >= 0:
            self._close_tab(index)

    def _navigate_current(self, target: str) -> None:
      resolved = self._resolve_omnibox_target(target)
      view = self.current_view()
      if view is not None:
        view.navigate(resolved)

    def _resolve_omnibox_target(self, target: str) -> str:
      stripped = target.strip()
      if not stripped:
        return HOME_URL

      if self._looks_like_link(stripped):
        return stripped

      return f"https://www.google.com/search?q={quote_plus(stripped)}"

    def _looks_like_link(self, value: str) -> bool:
      parsed = urlparse(value)
      if parsed.scheme in {"http", "https", "file", "about", "data"}:
        return True
      if value.startswith(("www.", "ftp.")):
        return True
      if Path(value).exists():
        return True
      if "/" in value or "\\" in value:
        return True
      if "." in value and " " not in value:
        return True
      return False

    def load_home(self) -> None:
        self._navigate_current(HOME_URL)

    def reload_current_tab(self) -> None:
        view = self.current_view()
        if view is not None:
            view.reload()

    def close_current_tab(self) -> None:
        self._close_tab(self.page_stack.currentIndex())

    def go_back(self) -> None:
        view = self.current_view()
        if view is not None:
            view.back()

    def go_forward(self) -> None:
        view = self.current_view()
        if view is not None:
            view.forward()

    def _close_tab(self, index: int) -> None:
        if index < 0 or self.page_stack.count() <= 1:
            return
        widget = self.page_stack.widget(index)
        if widget is None:
            return
        self.page_stack.removeWidget(widget)
        widget.deleteLater()
        self._reindex_tab_ids()
        if self.page_stack.currentIndex() < 0 and self.page_stack.count() > 0:
            self.page_stack.setCurrentIndex(0)
        self._sync_shell()

    def open_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            str(Path.home()),
            "Web Files (*.html *.htm *.txt *.md);;All Files (*.*)",
        )
        if selected:
            self._navigate_current(selected)
