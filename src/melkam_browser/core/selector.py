from __future__ import annotations

import re

from .dom import Element


def matches_selector(element: Element, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    if selector == "*":
        return True

    tag_name = None
    element_id = None
    class_name = None

    id_match = re.search(r"#([a-zA-Z_][\w\-]*)", selector)
    class_match = re.search(r"\.([a-zA-Z_][\w\-]*)", selector)
    tag_match = re.match(r"^[a-zA-Z][\w\-]*", selector)

    if tag_match:
        tag_name = tag_match.group(0).lower()
    if id_match:
        element_id = id_match.group(1)
    if class_match:
        class_name = class_match.group(1)

    if tag_name and element.tag != tag_name:
        return False
    if element_id and element.get_attribute("id") != element_id:
        return False
    if class_name:
        classes = (element.get_attribute("class") or "").split()
        if class_name not in classes:
            return False
    return True