from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..core.dom import Event, Element, TextNode, serialize_node
from ..core.page import BrowserPage


BOOTSTRAP_PREFIX = "__MELKAM_EVT__:"


class MelkamWebEnginePage(QWebEnginePage):
    bridge_event = Signal(str)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # noqa: N802
        if message.startswith(BOOTSTRAP_PREFIX):
            self.bridge_event.emit(message[len(BOOTSTRAP_PREFIX) :])
        # Ignore regular web-page console noise and only process bridge events.


class BrowserView(QWebEngineView):
    title_changed = Signal(str)
    url_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.page_model = BrowserPage(storage_root=Path.home() / ".melkam_browser")
        self.page_model.set_change_callback(self._sync_from_model)
        self._loading = False
        self._pending_dom_patches: list[str] = []
        self._python_mode = False
        self._python_dom_ready = False

        self.web_page = MelkamWebEnginePage(self)
        self.web_page.bridge_event.connect(self._handle_bridge_event)
        self.setPage(self.web_page)
        self._configure_engine()

        self.titleChanged.connect(self.title_changed.emit)
        self.urlChanged.connect(lambda url: self.url_changed.emit(url.toString()))
        self.loadFinished.connect(self._handle_load_finished)
        self.loadStarted.connect(lambda: self.status_changed.emit("Loading..."))

    def _trace(self, phase: str, detail: str) -> None:
        print(f"[{phase}] {detail}", flush=True)

    def closeEvent(self, event) -> None:
        """Clean up runtime when tab/view closes."""
        if self.page_model and hasattr(self.page_model, "python_runtime"):
            self.page_model.python_runtime.cleanup()
        super().closeEvent(event)

    def attach_devtools(self, inspector_view: QWebEngineView) -> None:
        self.page().setDevToolsPage(inspector_view.page())

    def _configure_engine(self) -> None:
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    @property
    def current_url(self) -> str:
        current = self.url().toString()
        return current or self.page_model.state.url

    def navigate(self, target: str) -> None:
        stripped = target.strip()
        if not stripped:
            return

        self._trace("NAV", f"navigate target={stripped}")

        if stripped.startswith("<"):
            self.load_html(stripped, url="about:blank")
            return

        resource = self.page_model.loader.load(stripped)
        has_python_script = re.search(r"type\s*=\s*['\"]?text/python['\"]?", resource.text, re.IGNORECASE) is not None
        if resource.content_type == "text/html" and has_python_script:
            self.load_html(resource.text, url=resource.url)
            return

        self._python_mode = False
        self._python_dom_ready = False
        native_url = self._to_qurl(resource.url if resource.url else stripped)
        if native_url.isValid():
            self._loading = True
            try:
                super().load(native_url)
            finally:
                self._loading = False
            self.status_changed.emit(native_url.toString())
            return

        fallback = self._to_qurl(stripped)
        if fallback.isValid():
            self._loading = True
            try:
                super().load(fallback)
            finally:
                self._loading = False
            self.status_changed.emit(fallback.toString())

    def load_html(self, html: str, url: str = "about:blank") -> None:
        self._python_mode = True
        self._python_dom_ready = False
        self._pending_dom_patches = []
        self._loading = True
        try:
            self.page_model.load_html(html, url=url)
            self.setHtml(self._build_html_document(), QUrl(url))
        finally:
            self._loading = False
        self.title_changed.emit(self.page_model.title())
        self.url_changed.emit(self.page_model.state.url)
        self.status_changed.emit(self.page_model.state.url)

    def reload(self) -> None:
        self._trace("NAV", "reload")
        if self._python_mode:
            self.load_html(self.page_model.state.source, url=self.page_model.state.url)
            return
        super().reload()

    def back(self) -> None:
        self._trace("NAV", "back")
        if self._python_mode:
            self.page_model.back()
            self.load_html(self.page_model.state.source, url=self.page_model.state.url)
            return
        super().back()

    def forward(self) -> None:
        self._trace("NAV", "forward")
        if self._python_mode:
            self.page_model.forward()
            self.load_html(self.page_model.state.source, url=self.page_model.state.url)
            return
        super().forward()

    def _build_html_document(self) -> str:
        body_html = "".join(_serialize_live_node(child) for child in self.page_model.document.root.children)
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset=\"utf-8\">
<style>
html, body {{ margin: 0; padding: 0; font-family: Segoe UI, Arial, sans-serif; background: #ffffff; color: #111111; }}
body {{ padding: 24px; line-height: 1.5; }}
button, input {{ font: inherit; }}
</style>
<script>
(function() {{
    if (window.__melkamBridgeInstalled) return;
    window.__melkamBridgeInstalled = true;
    const events = ['click', 'input', 'keydown', 'keyup', 'mousemove'];
    for (const kind of events) {{
        document.addEventListener(kind, function(event) {{
            let node = event.target;
            while (node && node !== document && (!node.id || node.id.length === 0)) {{
                node = node.parentElement;
            }}
            if (!node || !node.id) return;
            console.log('{BOOTSTRAP_PREFIX}' + JSON.stringify({{
                kind: kind,
                id: node.id,
                value: node.value || '',
                key: event.key || ''
            }}));
        }}, true);
    }}
}})();
</script>
</head>
<body>
{body_html}
</body>
</html>"""

    @Slot(str)
    def _handle_bridge_event(self, payload: str) -> None:
        self._trace("JS", f"bridge_event payload={payload[:80]}")
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return
        element = self.page_model.document.get_element_by_id(event.get("id", ""))
        if element is None:
            return
        element.dispatch(Event(type=event.get("kind", "").lower(), target=element, key=event.get("key", "")))

    def _handle_load_finished(self, ok: bool) -> None:
        self._trace("PAGE", f"load_finished ok={ok} python_mode={self._python_mode} dom_ready={self._python_dom_ready} pending_patches={len(self._pending_dom_patches)}")
        if not ok:
            self.status_changed.emit("Load failed")
            return
        if self._python_mode:
            self._python_dom_ready = True
            if self._pending_dom_patches:
                self._trace("JS", f"apply_pending_dom_patches count={len(self._pending_dom_patches)}")
                for patch in self._pending_dom_patches:
                    self.page().runJavaScript(patch)
                self._pending_dom_patches = []
            return
        page_title = self.title() or self.page().url().host() or self.page().url().toString()
        self.title_changed.emit(page_title)
        self.url_changed.emit(self.page().url().toString())
        self.status_changed.emit(self.page().url().toString())

    def _sync_from_model(self) -> None:
        if self._loading or not self._python_mode:
            return
        if not self.page_model.consume_dom_dirty():
            self._trace("DOM", "sync skipped no_dirty_dom")
            return
        self._trace("DOM", f"sync_from_model python_dom_ready={self._python_dom_ready}")
        patches = self._build_dom_patches()
        if self._python_dom_ready:
            for patch in patches:
                self._trace("JS", "runJavaScript DOM patch")
                self.page().runJavaScript(patch)
        else:
            self._pending_dom_patches.extend(patches)
            self._trace("DOM", f"queued DOM patches count={len(patches)}")
        self.title_changed.emit(self.page_model.title())
        self.url_changed.emit(self.page_model.state.url)
        self.status_changed.emit(self.page_model.state.url)

    def _build_dom_patches(self) -> list[str]:
        patches: list[str] = []
        for change in self.page_model.consume_dom_changes():
            node_id = change.get("node_id", "")
            if not node_id:
                continue
            selector = json.dumps(f'[data-melkam-id="{node_id}"]')
            if change["type"] == "text":
                patches.append(f"(function(){{const el=document.querySelector({selector}); if(el) el.textContent={json.dumps(change.get('text', ''))};}})();")
            elif change["type"] == "html":
                patches.append(f"(function(){{const el=document.querySelector({selector}); if(el) el.innerHTML={json.dumps(_serialize_html_fragment(change.get('html', '')))};}})();")
            elif change["type"] == "append":
                patches.append(f"(function(){{const el=document.querySelector({selector}); if(el) el.insertAdjacentHTML('beforeend', {json.dumps(_serialize_html_fragment(change.get('html', '')))});}})();")
            elif change["type"] == "remove":
                patches.append(f"(function(){{const el=document.querySelector({selector}); if(el) el.remove();}})();")
            elif change["type"] == "attr":
                name = json.dumps(change.get("name", ""))
                value = json.dumps(change.get("value", ""))
                patches.append(f"(function(){{const el=document.querySelector({selector}); if(el) el.setAttribute({name}, {value});}})();")
        return patches

    def _to_qurl(self, value: str) -> QUrl:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "file", "about", "data"}:
            return QUrl(value)
        path = Path(value)
        if path.exists():
            return QUrl.fromLocalFile(str(path.resolve()))
        return QUrl.fromUserInput(value)


def _serialize_live_node(node: Element | TextNode) -> str:
    if isinstance(node, TextNode):
        return node.text
    if isinstance(node, Element):
        if node.tag == "script":
            return ""
        attrs = {**node.attributes}
        if node.node_id:
            attrs["data-melkam-id"] = node.node_id
        attr_text = "".join(f' {name}="{value}"' for name, value in attrs.items())
        children = "".join(_serialize_live_node(child) for child in node.children)
        return f"<{node.tag}{attr_text}>{children}</{node.tag}>"
    return ""


def _serialize_html_fragment(html: str) -> str:
    from ..core.parser import HtmlParser

    fragment = HtmlParser().parse_fragment(html)
    return "".join(_serialize_live_node(child) for child in fragment.root.children)