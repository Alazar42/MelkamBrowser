from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional


class Node:
    def __init__(self, page: Any | None = None) -> None:
        self.page = page
        self.parent: Element | None = None


class TextNode(Node):
    def __init__(self, text: str, page: Any | None = None) -> None:
        super().__init__(page=page)
        self.text = text


@dataclass
class Event:
    type: str
    target: "Element"
    x: int = 0
    y: int = 0
    key: str = ""


class Element(Node):
    def __init__(self, tag: str, attributes: Optional[dict[str, str]] = None, page: Any | None = None) -> None:
        super().__init__(page=page)
        self.tag = tag.lower()
        self.attributes: dict[str, str] = attributes or {}
        self.node_id = self._allocate_node_id()
        self.children: list[Node] = []
        self.event_listeners: dict[str, list[Callable[[Event], None]]] = {}
        self.computed_style: dict[str, str] = {}
        self.layout_box: Any | None = None

    def _allocate_node_id(self) -> str:
        if self.page is not None and hasattr(self.page, "allocate_dom_node_id"):
            return self.page.allocate_dom_node_id()
        return ""

    @property
    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, TextNode):
                parts.append(child.text)
            elif isinstance(child, Element):
                parts.append(child.text)
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        self.children = [TextNode(value, page=self.page)]
        if self.page is not None and hasattr(self.page, "record_dom_change"):
            self.page.record_dom_change({"type": "text", "node_id": self.node_id, "text": value})
        self._invalidate()

    @property
    def html(self) -> str:
        return "".join(serialize_node(child) for child in self.children)

    @html.setter
    def html(self, value: str) -> None:
        if self.page is None:
            self.children = [TextNode(value)]
        else:
            from .parser import HtmlParser

            fragment = HtmlParser().parse_fragment(value, self.page)
            self.children = fragment.children
            for child in self.children:
                child.parent = self
            if hasattr(self.page, "record_dom_change"):
                self.page.record_dom_change({"type": "html", "node_id": self.node_id, "html": value})
        self._invalidate()

    def append(self, child: Node | str) -> Node:
        if isinstance(child, str):
            child = TextNode(child, page=self.page)
        child.parent = self
        child.page = self.page
        self.children.append(child)
        if self.page is not None and hasattr(self.page, "record_dom_change"):
            self.page.record_dom_change({"type": "append", "node_id": self.node_id, "html": serialize_node(child)})
        self._invalidate()
        return child

    def remove(self) -> None:
        if self.parent is None:
            return
        self.parent.children = [child for child in self.parent.children if child is not self]
        if self.page is not None and hasattr(self.page, "record_dom_change"):
            self.page.record_dom_change({"type": "remove", "node_id": self.node_id})
        self.parent._invalidate()
        self.parent = None

    def set_attribute(self, name: str, value: str) -> None:
        self.attributes[name.lower()] = value
        if self.page is not None and hasattr(self.page, "record_dom_change"):
            self.page.record_dom_change({"type": "attr", "node_id": self.node_id, "name": name.lower(), "value": value})
        self._invalidate()

    def get_attribute(self, name: str, default: str | None = None) -> str | None:
        return self.attributes.get(name.lower(), default)

    def on(self, event: str, callback: Callable[[Event], None]) -> None:
        self.event_listeners.setdefault(event.lower(), []).append(callback)

    def dispatch(self, event: Event) -> None:
        for callback in self.event_listeners.get(event.type.lower(), []):
            callback(event)

    def query(self, selector: str) -> "Element | None":
        matches = self.query_all(selector)
        return matches[0] if matches else None

    def query_all(self, selector: str) -> list["Element"]:
        from .selector import matches_selector

        result: list[Element] = []
        for element in iter_elements(self):
            if matches_selector(element, selector):
                result.append(element)
        return result

    def _invalidate(self) -> None:
        if self.page is not None and getattr(self.page, "suspend_invalidation", False):
            return
        if self.page is not None and hasattr(self.page, "invalidate"):
            self.page.invalidate()


class Document(Node):
    def __init__(self, page: Any | None = None) -> None:
        super().__init__(page=page)
        self.root = Element("document", page=page)
        self.root.parent = None

    def query(self, selector: str) -> Element | None:
        matches = self.query_all(selector)
        return matches[0] if matches else None

    def query_all(self, selector: str) -> list[Element]:
        from .selector import matches_selector

        return [element for element in iter_elements(self.root) if matches_selector(element, selector)]

    def create_element(self, tag: str) -> Element:
        return Element(tag, page=self.page)

    def get_element_by_id(self, element_id: str) -> Element | None:
        for element in iter_elements(self.root):
            if element.get_attribute("id") == element_id:
                return element
        return None


def iter_elements(node: Node) -> Iterable[Element]:
    if isinstance(node, Element):
        yield node
        for child in node.children:
            yield from iter_elements(child)


def serialize_node(node: Node) -> str:
    if isinstance(node, TextNode):
        return node.text
    if isinstance(node, Element):
        attrs = "".join(f' {name}="{value}"' for name, value in node.attributes.items())
        children = "".join(serialize_node(child) for child in node.children)
        return f"<{node.tag}{attrs}>{children}</{node.tag}>"
    return ""