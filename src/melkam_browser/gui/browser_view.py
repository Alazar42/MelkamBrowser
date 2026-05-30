from __future__ import annotations

import html
import json
import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import url2pathname
from urllib.parse import urljoin, urlparse

from PySide6.QtCore import QObject, QUrl, Signal, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..core.network import ResourceLoader
from ..core.parser import HtmlParser


PYTHON_SCRIPT_TYPE = "text/python"
PYTHON_EVENT_PREFIX = "__MELKAM_PY_EVT__:"


@dataclass
class BrowserEvent:
    type: str
    key: str = ""
    value: str = ""


class _JsBridge(QObject):
    request = Signal(int, str)
    response = Signal(int, object)


class _ChromiumPage(QWebEnginePage):
    bridge_event = Signal(str)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # noqa: N802
        if message.startswith(PYTHON_EVENT_PREFIX):
            self.bridge_event.emit(message[len(PYTHON_EVENT_PREFIX) :])


class _PythonWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, callback: Callable[[], None]) -> None:
        self._queue.put(callback)

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            callback = self._queue.get()
            if callback is None:
                return
            try:
                callback()
            except Exception as exc:
                print(f"[PY] worker error: {exc}", flush=True)


class JSBridge:
    def __init__(self, view: "BrowserView") -> None:
        self.view = view

    def eval(self, script: str) -> Any:
        return self.view.evaluate_js_sync(script)


class ElementBuilder:
    def __init__(self, tag: str) -> None:
        self.tag = tag.lower()
        self.attributes: dict[str, str] = {}
        self.children: list[ElementBuilder | str] = []
        self._html: str | None = None

    @property
    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                parts.append(child.to_html())
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        self._html = None
        self.children = [value]

    @property
    def html(self) -> str:
        if self._html is not None:
            return self._html
        return "".join(child if isinstance(child, str) else child.to_html() for child in self.children)

    @html.setter
    def html(self, value: str) -> None:
        self._html = value
        self.children = []

    def set_attribute(self, name: str, value: str) -> None:
        self.attributes[name.lower()] = value

    def append(self, child: "ElementBuilder | str") -> None:
        self._html = None
        self.children.append(child)

    def to_html(self) -> str:
        attrs = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in self.attributes.items())
        children = self._html if self._html is not None else "".join(child if isinstance(child, str) else child.to_html() for child in self.children)
        return f"<{self.tag}{attrs}>{children}</{self.tag}>"


class ElementProxy:
    def __init__(self, view: "BrowserView", selector: str) -> None:
        self.view = view
        self.selector = selector

    def _query(self, expression: str) -> Any:
        return self.view.evaluate_js_sync(expression)

    @property
    def text(self) -> str:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(!el) return ''; if('value' in el) return el.value; return el.textContent || ''; }})()"
        return str(self._query(script) or "")

    @text.setter
    def text(self, value: str) -> None:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(!el) return; if('value' in el) {{ el.value={json.dumps(value)}; }} else {{ el.textContent={json.dumps(value)}; }} }})()"
        self._query(script)

    @property
    def html(self) -> str:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); return el ? el.innerHTML : ''; }})()"
        return str(self._query(script) or "")

    @html.setter
    def html(self, value: str) -> None:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(el) el.innerHTML={json.dumps(value)}; }})()"
        self._query(script)

    def set_attribute(self, name: str, value: str) -> None:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(el) el.setAttribute({json.dumps(name)}, {json.dumps(value)}); }})()"
        self._query(script)

    def get_attribute(self, name: str, default: str | None = None) -> str | None:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); return el ? el.getAttribute({json.dumps(name)}) : null; }})()"
        result = self._query(script)
        return default if result in {None, "", False} else str(result)

    def append(self, child: ElementBuilder | str | "ElementProxy") -> None:
        if isinstance(child, ElementBuilder):
            fragment = child.to_html()
        elif isinstance(child, ElementProxy):
            fragment = child.html
        else:
            fragment = html.escape(child)
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(el) el.insertAdjacentHTML('beforeend', {json.dumps(fragment)}); }})()"
        self._query(script)

    def remove(self) -> None:
        script = f"(function(){{const el=document.querySelector({json.dumps(self.selector)}); if(el) el.remove(); }})()"
        self._query(script)

    def on(self, event: str, callback: Callable[[BrowserEvent], None]) -> None:
        self.view._register_event_handler(self.selector, event, callback)

    def query(self, selector: str) -> "ElementProxy | None":
        nested = f"{self.selector} {selector}"
        return self.view.query_selector(nested)


class DocumentProxy:
    def __init__(self, view: "BrowserView") -> None:
        self.view = view
        self.js = JSBridge(view)

    def query(self, selector: str) -> ElementProxy | None:
        return self.view.query_selector(selector)

    def querySelector(self, selector: str) -> ElementProxy | None:  # noqa: N802
        return self.query(selector)

    def create_element(self, tag: str) -> ElementBuilder:
        return ElementBuilder(tag)

    def createElement(self, tag: str) -> ElementBuilder:  # noqa: N802
        return self.create_element(tag)


class BrowserView(QWebEngineView):
    title_changed = Signal(str)
    url_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loader = ResourceLoader()
        self._python_scripts: list[str] = []
        self._python_worker = _PythonWorker()
        self._js_bridge = _JsBridge()
        self._js_bridge.request.connect(self._execute_js_request, Qt.ConnectionType.QueuedConnection)
        self._js_bridge.response.connect(self._deliver_js_result, Qt.ConnectionType.QueuedConnection)
        self._js_waits: dict[int, tuple[threading.Event, dict[str, Any]]] = {}
        self._next_js_request_id = 1
        self._event_handlers: dict[str, Callable[[BrowserEvent], None]] = {}
        self._next_event_handler_id = 1
        self._pending_source_html = ""

        self.web_page = _ChromiumPage(self)
        self.web_page.bridge_event.connect(self._handle_bridge_event)
        self.setPage(self.web_page)
        self._configure_engine()

        self.titleChanged.connect(self.title_changed.emit)
        self.urlChanged.connect(lambda url: self.url_changed.emit(url.toString()))
        self.loadStarted.connect(lambda: self.status_changed.emit("Loading..."))
        self.loadFinished.connect(self._handle_load_finished)

    def _trace(self, phase: str, detail: str) -> None:
        print(f"[{phase}] {detail}", flush=True)

    def _configure_engine(self) -> None:
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._python_worker.stop()
        super().closeEvent(event)

    def attach_devtools(self, inspector_view: QWebEngineView) -> None:
        self.page().setDevToolsPage(inspector_view.page())

    @property
    def current_url(self) -> str:
        current = self.url().toString()
        return current or self.page().url().toString()

    def navigate(self, target: str) -> None:
        stripped = target.strip()
        if not stripped:
            return

        self._trace("NAV", f"navigate target={stripped}")

        if stripped.startswith("<"):
            self.load_html(stripped, url="about:blank")
            return

        if self._looks_like_local_html(stripped):
            resource = self._loader.load(stripped)
            if resource.content_type == "text/html" and self._contains_python_script(resource.text):
                self.load_html(resource.text, url=resource.url)
                return

        self._python_scripts = []
        native_url = self._to_qurl(stripped)
        if native_url.isValid():
            super().load(native_url)
            return

        self.load_html(stripped, url="about:blank")

    def load_html(self, html_source: str, url: str = "about:blank") -> None:
        self._trace("NAV", f"load_html url={url}")
        sanitized_html, scripts = self._sanitize_html_and_extract_python(html_source, url)
        self._pending_source_html = html_source
        self._python_scripts = scripts
        super().setHtml(sanitized_html, QUrl(url))

    def reload(self) -> None:
        self._trace("NAV", "reload")
        if self._python_scripts and self._pending_source_html:
            self.load_html(self._pending_source_html, url=self.current_url)
            return
        super().reload()

    def back(self) -> None:
        self._trace("NAV", "back")
        super().back()

    def forward(self) -> None:
        self._trace("NAV", "forward")
        super().forward()

    def query_selector(self, selector: str) -> ElementProxy | None:
        exists = self.evaluate_js_sync(f"(function(){{return !!document.querySelector({json.dumps(selector)});}})()")
        if not exists:
            return None
        return ElementProxy(self, selector)

    def evaluate_js_sync(self, script: str, timeout: float = 10.0) -> Any:
        request_id = self._next_js_request_id
        self._next_js_request_id += 1
        done = threading.Event()
        box: dict[str, Any] = {}
        self._js_waits[request_id] = (done, box)
        self._js_bridge.request.emit(request_id, script)
        if not done.wait(timeout):
            self._js_waits.pop(request_id, None)
            raise TimeoutError("JavaScript evaluation timed out")
        return box.get("value")

    def _execute_js_request(self, request_id: int, script: str) -> None:
        self.page().runJavaScript(script, lambda value, rid=request_id: self._js_bridge.response.emit(rid, value))

    def _deliver_js_result(self, request_id: int, value: Any) -> None:
        pending = self._js_waits.pop(request_id, None)
        if pending is None:
            return
        event, box = pending
        box["value"] = value
        event.set()

    def _handle_load_finished(self, ok: bool) -> None:
        self._trace("PAGE", f"load_finished ok={ok} python_scripts={len(self._python_scripts)}")
        if not ok:
            self.status_changed.emit("Load failed")
            return

        if self._python_scripts:
            document = DocumentProxy(self)
            for code in self._python_scripts:
                self._python_worker.submit(lambda source=code: self._execute_python_script(source, document))

        page_title = self.title() or self.page().url().host() or self.page().url().toString()
        self.title_changed.emit(page_title)
        self.url_changed.emit(self.page().url().toString())
        self.status_changed.emit(self.page().url().toString())

    def _execute_python_script(self, code: str, document: DocumentProxy) -> None:
        globals_dict = {
            "__builtins__": {
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "max": max,
                "min": min,
                "print": print,
                "range": range,
                "round": round,
                "set": set,
                "str": str,
                "sum": sum,
                "tuple": tuple,
                "zip": zip,
            },
            "__name__": "__main__",
            "document": document,
            "js": document.js,
            "window": type("WindowProxy", (), {"document": document, "js": document.js})(),
            "console": type("ConsoleProxy", (), {"log": staticmethod(print), "warn": staticmethod(print), "error": staticmethod(print)})(),
        }
        try:
            exec(code, globals_dict, globals_dict)
        except Exception as exc:
            print(f"[PY] script error: {exc}", flush=True)

    def _handle_bridge_event(self, payload: str) -> None:
        try:
            event_data = json.loads(payload)
        except json.JSONDecodeError:
            return
        handler_id = event_data.get("handler_id", "")
        callback = self._event_handlers.get(handler_id)
        if callback is None:
            return

        event = BrowserEvent(
            type=str(event_data.get("type", "")),
            key=str(event_data.get("key", "")),
            value=str(event_data.get("value", "")),
        )
        self._python_worker.submit(lambda: callback(event))

    def _register_event_handler(self, selector: str, event: str, callback: Callable[[BrowserEvent], None]) -> None:
        handler_id = f"evt_{self._next_event_handler_id}"
        self._next_event_handler_id += 1
        self._event_handlers[handler_id] = callback
        script = f"""
(function() {{
    const element = document.querySelector({json.dumps(selector)});
    if (!element) return;
    element.addEventListener({json.dumps(event)}, function(ev) {{
        console.log({json.dumps(PYTHON_EVENT_PREFIX)} + JSON.stringify({{
            handler_id: {json.dumps(handler_id)},
            type: ev.type,
            key: ev.key || '',
            value: element.value || ''
        }}));
    }}, true);
}})();
"""
        self.evaluate_js_sync(script)

    def _sanitize_html_and_extract_python(self, html_source: str, url: str) -> tuple[str, list[str]]:
        document = HtmlParser().parse(html_source, page=None)
        scripts: list[str] = []

        def _serialize(node: Any) -> str:
            from ..core.dom import Element, TextNode

            if isinstance(node, TextNode):
                return html.escape(node.text)
            if isinstance(node, Element):
                if node.tag == "script" and (node.get_attribute("type") or "text/javascript") == PYTHON_SCRIPT_TYPE:
                    source = node.get_attribute("src")
                    if source:
                        scripts.append(self._load_external_python_script(source, url))
                    elif node.text.strip():
                        scripts.append(node.text)
                    return ""

                attrs = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in node.attributes.items())
                children = "".join(_serialize(child) for child in node.children)
                return f"<{node.tag}{attrs}>{children}</{node.tag}>"
            return ""

        sanitized = "".join(_serialize(child) for child in document.root.children)
        return sanitized, [script for script in scripts if script]

    def _load_external_python_script(self, source: str, page_url: str) -> str:
        target = source.strip()
        if not target:
            return ""

        parsed_current = urlparse(page_url)
        parsed_target = urlparse(target)

        if parsed_target.scheme in {"http", "https", "file"}:
            resolved = target
        elif parsed_current.scheme == "file":
            # Decode file URLs like file:///C:/path into a native Windows path.
            current_file_path = Path(url2pathname(parsed_current.path))
            base_dir = current_file_path.parent if current_file_path.suffix else current_file_path
            resolved = str((base_dir / target).resolve())
        elif parsed_current.scheme in {"http", "https"}:
            resolved = urljoin(page_url, target)
        else:
            resolved = target

        try:
            resource = self._loader.load(resolved)
        except Exception:
            return ""
        return resource.text if resource.text else ""

    def _contains_python_script(self, html_source: str) -> bool:
        return re.search(r"type\s*=\s*['\"]?text/python['\"]?", html_source, re.IGNORECASE) is not None

    def _looks_like_local_html(self, target: str) -> bool:
        return target.lower().endswith((".html", ".htm", ".xhtml", ".txt", ".md")) or Path(target).exists()

    def _to_qurl(self, value: str) -> QUrl:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "file", "about", "data"}:
            return QUrl(value)
        path = Path(value)
        if path.exists():
            return QUrl.fromLocalFile(str(path.resolve()))
        return QUrl.fromUserInput(value)
