from __future__ import annotations

from dataclasses import dataclass, field
import re

from .dom import Element, TextNode


@dataclass
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass
class LayoutBox:
    node: Element | TextNode | None
    rect: Rect
    children: list["LayoutBox"] = field(default_factory=list)


class LayoutEngine:
    def layout(self, document: object, viewport_width: int) -> LayoutBox:
        from .dom import Document

        assert isinstance(document, Document)
        root = LayoutBox(None, Rect(0, 0, viewport_width, 0), [])
        cursor_y = 0
        for child in document.root.children:
            child_box, cursor_y = self._layout_node(child, 16, cursor_y + 12, viewport_width - 32)
            if child_box is not None:
                root.children.append(child_box)
        root.rect.height = max(cursor_y + 24, 1)
        return root

    def _layout_node(self, node: Element | TextNode, x: int, y: int, width: int) -> tuple[LayoutBox | None, int]:
        if isinstance(node, TextNode):
            text = node.text.strip()
            if not text:
                return None, y
            height = 20
            rect = Rect(x, y, min(width, max(16, len(text) * 8)), height)
            return LayoutBox(node, rect, []), y + height

        style = node.computed_style or {}
        if style.get("display") == "none" or node.tag in {"script", "style"}:
            return None, y
        display = style.get("display", "block")
        padding = _parse_box_value(style.get("padding", "0"))
        margin = _parse_box_value(style.get("margin", "0"))
        font_size = _parse_font_size(style.get("font-size", "16"))
        line_height = max(font_size + 8, 22)
        content_width = max(40, width - margin[1] - margin[3])

        if display in {"inline", "inline-block"}:
            text = node.text.strip() or node.tag.upper()
            calculated_width = min(content_width, max(40, len(text) * max(7, font_size // 2) + padding[1] + padding[3]))
            calculated_height = line_height + padding[0] + padding[2]
            box = LayoutBox(node, Rect(x, y, calculated_width, calculated_height), [])
            node.layout_box = box
            return box, y + calculated_height + margin[2]

        box = LayoutBox(node, Rect(x, y, content_width, 0), [])
        node.layout_box = box
        inner_y = y + padding[0] + margin[0]
        child_y = inner_y

        text_children = [child for child in node.children if isinstance(child, TextNode) and child.text.strip()]
        element_children = [child for child in node.children if isinstance(child, Element)]

        if text_children and not element_children:
            text = " ".join(child.text.strip() for child in text_children if child.text.strip())
            text_height = line_height + padding[2]
            text_box = LayoutBox(TextNode(text), Rect(x + padding[3], child_y, max(40, len(text) * max(7, font_size // 2)), text_height), [])
            box.children.append(text_box)
            child_y += text_height
        else:
            for child in node.children:
                child_box, child_y = self._layout_node(child, x + padding[3], child_y, content_width - padding[1] - padding[3])
                if child_box is not None:
                    box.children.append(child_box)

        total_height = max(child_y - y + padding[2], line_height + padding[0] + padding[2])
        box.rect.height = total_height + margin[2]
        return box, y + total_height + margin[2]


def _parse_box_value(value: str) -> tuple[int, int, int, int]:
    parts = [_coerce_length(part, 0) for part in value.split() if part]
    if not parts:
        return (0, 0, 0, 0)
    if len(parts) == 1:
        return (parts[0], parts[0], parts[0], parts[0])
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    return tuple(parts[:4])  # type: ignore[return-value]


def _parse_font_size(value: str) -> int:
    cleaned = value.strip().lower()
    if not cleaned:
        return 16
    if cleaned.endswith("%"):
        try:
            return max(8, int(round(16 * float(cleaned[:-1]) / 100.0)))
        except ValueError:
            return 16
    return max(8, _coerce_length(cleaned, 16))


def _coerce_length(value: str, default: int) -> int:
    cleaned = value.strip().lower().replace("px", "")
    if not cleaned:
        return default
    match = re.match(r"^-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return default
    try:
        return int(round(float(match.group(0))))
    except ValueError:
        return default