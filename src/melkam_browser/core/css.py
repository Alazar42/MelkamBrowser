from __future__ import annotations

from dataclasses import dataclass
import re

from .dom import Document, Element, iter_elements


DEFAULT_STYLES: dict[str, str] = {
    "display": "block",
    "margin": "0",
    "padding": "0",
    "border": "0",
    "background-color": "transparent",
    "color": "#111111",
    "font-size": "16",
    "width": "auto",
    "height": "auto",
}

INLINE_DISPLAY = {"span", "a", "button", "strong", "em", "label"}
BLOCK_DISPLAY = {"html", "head", "body", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "form", "style", "script"}


@dataclass
class CssRule:
    selector: str
    declarations: dict[str, str]


class CssParser:
    def parse(self, css_text: str) -> list[CssRule]:
        rules: list[CssRule] = []
        for selector, body in re.findall(r"([^{}]+)\{([^{}]+)\}", css_text, flags=re.S):
            declarations: dict[str, str] = {}
            for declaration in body.split(";"):
                if ":" not in declaration:
                    continue
                name, value = declaration.split(":", 1)
                declarations[name.strip().lower()] = value.strip()
            for part in selector.split(","):
                part = part.strip()
                if part:
                    rules.append(CssRule(part, declarations.copy()))
        return rules


class StyleResolver:
    def __init__(self) -> None:
        self.parser = CssParser()

    def resolve(self, document: Document, stylesheets: list[str]) -> None:
        rules: list[CssRule] = []
        for stylesheet in stylesheets:
            rules.extend(self.parser.parse(stylesheet))

        for element in iter_elements(document.root):
            style = dict(DEFAULT_STYLES)
            if element.tag in BLOCK_DISPLAY:
                style["display"] = "block"
            if element.tag in INLINE_DISPLAY:
                style["display"] = "inline"
            if element.tag == "button":
                style.update({"display": "inline-block", "padding": "8", "border": "1px solid #444", "background-color": "#ededed"})
            if element.tag == "input":
                style.update({"display": "inline-block", "padding": "6", "border": "1px solid #777", "background-color": "#ffffff"})
            if element.tag == "a":
                style.update({"color": "#0b57d0"})
            if element.tag.startswith("h") and len(element.tag) == 2 and element.tag[1].isdigit():
                size = 36 - (int(element.tag[1]) - 1) * 4
                style.update({"font-size": str(size), "margin": "12 0"})

            for rule in rules:
                if _matches_rule(element, rule.selector):
                    style.update(rule.declarations)

            inline_style = element.get_attribute("style") or ""
            for declaration in inline_style.split(";"):
                if ":" not in declaration:
                    continue
                name, value = declaration.split(":", 1)
                style[name.strip().lower()] = value.strip()

            element.computed_style = style


def _matches_rule(element: Element, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    if selector.startswith("#"):
        return element.get_attribute("id") == selector[1:]
    if selector.startswith("."):
        classes = (element.get_attribute("class") or "").split()
        return selector[1:] in classes
    return element.tag == selector.lower()