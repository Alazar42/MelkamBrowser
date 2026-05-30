from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import url2pathname
from urllib.parse import urljoin, urlparse

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from .css import StyleResolver
from .dom import Document, Element, Event, TextNode
from .layout import LayoutBox, LayoutEngine
from .network import ResourceLoader
from .runtime import PythonRuntime
from .storage import BrowserDatabase, LocalStorage, SessionStorage
from .parser import HtmlParser


@dataclass
class PageState:
    url: str
    source: str
    resource_type: str


class BrowserPage:
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.loader = ResourceLoader()
        self.resolver = StyleResolver()
        self.layout_engine = LayoutEngine()
        self.python_runtime = PythonRuntime(self)
        self.database = BrowserDatabase(self.storage_root / "browser.sqlite3")
        self.local_storage = LocalStorage(self.database)
        self.session_storage = SessionStorage()
        self.on_change: Callable[[], None] | None = None
        self._next_dom_node_id = 1
        self._dom_changes: list[dict[str, str]] = []
        self.document = Document(page=self)
        self.layout_root: LayoutBox | None = None
        self.state = PageState(url="about:blank", source="", resource_type="text/html")
        self._history: list[PageState] = []
        self._history_index = -1
        self.suspend_invalidation = False
        self._dom_dirty = False
        self._console_log: list[tuple[str, str]] = []
        self._trace_log: list[str] = []

    def allocate_dom_node_id(self) -> str:
        node_id = f"n{self._next_dom_node_id}"
        self._next_dom_node_id += 1
        return node_id

    def record_dom_change(self, change: dict[str, str]) -> None:
        self._dom_changes.append(change)

    def _trace(self, phase: str, detail: str) -> None:
        message = f"[{phase}] {detail}"
        self._trace_log.append(message)
        print(message, flush=True)

    def _on_console(self, level: str, message: str) -> None:
        """Callback for console messages from the Python runtime."""
        self._console_log.append((level, message))

    def set_change_callback(self, callback: Callable[[], None]) -> None:
        self.on_change = callback

    def invalidate(self) -> None:
        self._trace("DOM", f"invalidate url={self.state.url}")
        self._dom_dirty = True
        self.reflow()
        if self.on_change is not None:
            self.on_change()

    def consume_dom_dirty(self) -> bool:
        dirty = self._dom_dirty
        self._dom_dirty = False
        return dirty

    def consume_dom_changes(self) -> list[dict[str, str]]:
        changes = list(self._dom_changes)
        self._dom_changes.clear()
        return changes

    def load(self, target: str) -> None:
        self._trace("NAV", f"load target={target}")
        resource = self.loader.load(target)
        self._push_history(PageState(url=resource.url, source=resource.text, resource_type=resource.content_type))
        self._load_html(resource.text)

    def load_html(self, html: str, url: str = "about:blank") -> None:
        self._trace("NAV", f"load_html url={url}")
        self._push_history(PageState(url=url, source=html, resource_type="text/html"))
        self._load_html(html)

    def back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_history()

    def forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_history()

    def reload(self) -> None:
        self._trace("NAV", "reload")
        if not self._history:
            return
        current = self._history[self._history_index]
        if current.url == "about:blank" or current.url.startswith("data:") or current.url.startswith("file:"):
            self._load_html(current.source)
            return
        self.load(current.url)

    def _push_history(self, state: PageState) -> None:
        self._history = self._history[: self._history_index + 1]
        self._history.append(state)
        self._history_index = len(self._history) - 1
        self.state = state

    def _restore_history(self) -> None:
        self.state = self._history[self._history_index]
        self._load_html(self.state.source)

    def _load_html(self, html: str) -> None:
        self._trace("PAGE", f"parse_and_build url={self.state.url}")
        self._dom_dirty = False
        self._dom_changes.clear()
        self.document = HtmlParser().parse(html, page=self)
        stylesheets: list[str] = []
        scripts: list[str] = []

        for element in self.document.query_all("style"):
            stylesheets.append(element.text)
        for script in self.document.query_all("script"):
            if (script.get_attribute("type") or "text/javascript") == "text/python":
                source = script.get_attribute("src")
                if source:
                    code = self._load_external_python_script(source)
                    if code:
                        scripts.append(code)
                elif script.text.strip():
                    scripts.append(script.text)

        self.resolver.resolve(self.document, stylesheets)
        self._trace("LAYOUT", f"reflow-start url={self.state.url}")
        self.layout_root = self.layout_engine.layout(self.document, 1024)

        for code in scripts:
            self._trace("PY", f"execute bytes={len(code)} url={self.state.url}")
            self.python_runtime.execute(code, self.document)

        self.reflow()
        self._dom_dirty = False
        self._dom_changes.clear()
        if self.on_change is not None:
            self.on_change()
        self.database.record_visit(self.state.url, self.title(), self.state.resource_type)

    def _load_external_python_script(self, source: str) -> str:
        target = source.strip()
        if not target:
            return ""

        parsed_current = urlparse(self.state.url)
        parsed_target = urlparse(target)

        if parsed_target.scheme in {"http", "https", "file"}:
            resolved = target
        elif parsed_current.scheme == "file":
            base_path = Path(url2pathname(parsed_current.path))
            if base_path.suffix:
                base_dir = base_path.parent
            else:
                base_dir = base_path
            resolved = str((base_dir / target).resolve())
        elif parsed_current.scheme in {"http", "https"}:
            resolved = urljoin(self.state.url, target)
        else:
            resolved = target

        try:
            resource = self.loader.load(resolved)
        except Exception:
            return ""
        return resource.text if resource.text else ""

    def reflow(self, viewport_width: int = 1024) -> None:
        self._trace("LAYOUT", f"recalculate viewport={viewport_width} url={self.state.url}")
        self.resolver.resolve(self.document, [element.text for element in self.document.query_all("style")])
        self.layout_root = self.layout_engine.layout(self.document, viewport_width)

    def title(self) -> str:
        title_element = self.document.query("title")
        if title_element is not None and title_element.text.strip():
            return title_element.text.strip()
        heading = self.document.query("h1")
        if heading is not None and heading.text.strip():
            return heading.text.strip()
        return self.state.url

    def hit_test(self, x: int, y: int) -> Element | None:
        if self.layout_root is None:
            return None

        best = self._hit_test_box(self.layout_root, x, y)
        return best.node if best and isinstance(best.node, Element) else None

    def _hit_test_box(self, box: LayoutBox, x: int, y: int) -> LayoutBox | None:
        for child in reversed(box.children):
            hit = self._hit_test_box(child, x, y)
            if hit is not None:
                return hit
        if box.rect.contains(x, y):
            return box
        return None

    def dispatch_click(self, x: int, y: int) -> None:
        target = self.hit_test(x, y)
        if target is None:
            return
        target.dispatch(Event(type="click", target=target, x=x, y=y))
        href = target.get_attribute("href")
        if target.tag == "a" and href:
            self.load(href)

    def render(self, painter: QPainter, width: int, height: int) -> None:
        self._trace("PAINT", f"render width={width} height={height} url={self.state.url}")
        painter.save()
        painter.fillRect(0, 0, width, height, QColor("#ffffff"))
        if self.layout_root is None:
            painter.setPen(QPen(QColor("#666666")))
            painter.drawText(QRectF(20, 20, width - 40, 40), Qt.AlignmentFlag.AlignLeft, "Loading...")
            painter.restore()
            return
        self._render_box(painter, self.layout_root)
        painter.restore()

    def _render_box(self, painter: QPainter, box: LayoutBox) -> None:
        if isinstance(box.node, Element):
            self._render_element(painter, box)
        elif isinstance(box.node, TextNode):
            self._render_text(painter, box)
        for child in box.children:
            self._render_box(painter, child)

    def _render_element(self, painter: QPainter, box: LayoutBox) -> None:
        node = box.node
        style = node.computed_style or {}
        rect = box.rect
        background = style.get("background-color", "transparent")
        border = style.get("border", "0")
        color = QColor(style.get("color", "#111111"))
        font_size = int(float(style.get("font-size", "16")))

        if background != "transparent":
            painter.fillRect(QRectF(rect.x, rect.y, rect.width, rect.height), QColor(background))

        if border != "0":
            painter.setPen(QPen(QColor("#444444"), 1))
            painter.drawRect(rect.x, rect.y, rect.width, rect.height)

        painter.setPen(QPen(color))
        font = QFont()
        font.setPointSize(font_size)
        painter.setFont(font)

        if node.tag in {"button", "input"}:
            text = node.text.strip() or node.get_attribute("value") or node.tag
            painter.drawText(QRectF(rect.x + 10, rect.y + 4, rect.width - 20, rect.height - 8), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        elif node.tag == "a":
            painter.drawText(QRectF(rect.x, rect.y, rect.width, rect.height), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, node.text.strip())

    def _render_text(self, painter: QPainter, box: LayoutBox) -> None:
        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#111111")))
        painter.drawText(QRectF(box.rect.x, box.rect.y, box.rect.width, box.rect.height), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, box.node.text)