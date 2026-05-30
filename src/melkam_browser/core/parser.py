from __future__ import annotations

from dataclasses import dataclass
import re

from .dom import Document, Element, TextNode


SELF_CLOSING_TAGS = {"img", "input", "br", "hr", "meta", "link"}


@dataclass
class Token:
    kind: str
    value: str
    attributes: dict[str, str] | None = None
    closing: bool = False
    self_closing: bool = False


class HtmlParser:
    def parse(self, source: str, page: object | None = None) -> Document:
        document = Document(page=page)
        self._build_tree(document, source)
        return document

    def parse_fragment(self, source: str, page: object | None = None) -> Document:
        return self.parse(source, page=page)

    def _build_tree(self, document: Document, source: str) -> None:
        page = document.page
        if page is not None:
            setattr(page, "suspend_invalidation", True)

        try:
            tokens = list(self._tokenize(source))
            stack: list[Element] = [document.root]

            for token in tokens:
                if token.kind == "text":
                    if token.value:
                        stack[-1].append(TextNode(token.value, page=document.page))
                    continue

                if token.closing:
                    for index in range(len(stack) - 1, 0, -1):
                        if stack[index].tag == token.value:
                            stack = stack[:index]
                            break
                    continue

                element = Element(token.value, token.attributes or {}, page=document.page)
                stack[-1].append(element)

                if not token.self_closing and element.tag not in SELF_CLOSING_TAGS:
                    stack.append(element)
        finally:
            if page is not None:
                setattr(page, "suspend_invalidation", False)

    def _tokenize(self, source: str):
        position = 0
        length = len(source)

        while position < length:
            if source[position] != "<":
                next_tag = source.find("<", position)
                if next_tag == -1:
                    next_tag = length
                text = source[position:next_tag]
                yield Token("text", text)
                position = next_tag
                continue

            if source.startswith("<!--", position):
                end_comment = source.find("-->", position + 4)
                position = length if end_comment == -1 else end_comment + 3
                continue

            end = source.find(">", position + 1)
            if end == -1:
                yield Token("text", source[position:])
                break

            raw_tag = source[position + 1 : end].strip()
            position = end + 1

            if not raw_tag:
                continue

            if raw_tag.startswith("!"):
                continue

            closing = raw_tag.startswith("/")
            if closing:
                yield Token("tag", raw_tag[1:].strip().lower(), closing=True)
                continue

            self_closing = raw_tag.endswith("/")
            if self_closing:
                raw_tag = raw_tag[:-1].rstrip()

            parts = raw_tag.split(None, 1)
            tag_name = parts[0].lower()
            attribute_text = parts[1] if len(parts) > 1 else ""
            attributes = self._parse_attributes(attribute_text)

            if tag_name in {"script", "style"}:
                close_tag = f"</{tag_name}>"
                end_script = source.lower().find(close_tag, position)
                script_text = source[position:end_script] if end_script != -1 else source[position:]
                position = length if end_script == -1 else end_script + len(close_tag)
                yield Token("tag", tag_name, attributes=attributes)
                if script_text:
                    yield Token("text", script_text)
                yield Token("tag", tag_name, closing=True)
                continue

            yield Token("tag", tag_name, attributes=attributes, self_closing=self_closing)

    def _parse_attributes(self, text: str) -> dict[str, str]:
        attributes: dict[str, str] = {}
        for name, double_quoted, single_quoted, bare in re.findall(
            r'([a-zA-Z_:][\w:.-]*)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'>/=]+)))?',
            text,
        ):
            attributes[name.lower()] = double_quoted or single_quoted or bare or ""
        return attributes