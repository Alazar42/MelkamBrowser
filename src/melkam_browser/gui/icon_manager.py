from __future__ import annotations

from pathlib import Path
from typing import Dict

from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets" / "icons"


class IconManager:
    def __init__(self, theme: str = "dark") -> None:
        self.theme = theme
        self._cache: Dict[str, QIcon] = {}

    def _svg_path(self, name: str) -> Path:
        return ASSETS_DIR / f"{name}.svg"

    def icon(self, name: str, size: int = 20) -> QIcon:
        key = f"{name}:{size}:{self.theme}"
        if key in self._cache:
            return self._cache[key]

        path = self._svg_path(name)
        if not path.exists():
            return QIcon()

        renderer = QSvgRenderer(str(path))
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()

        # Tint icon according to theme by applying source-in color
        color = QColor("#E8EAED") if self.theme == "dark" else QColor("#0D1117")
        tinted = QPixmap(pix.size())
        tinted.fill(QColor(0, 0, 0, 0))
        p = QPainter(tinted)
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(tinted.rect(), color)
        p.end()

        icon = QIcon(tinted)
        self._cache[key] = icon
        return icon


_global_icon_manager: IconManager | None = None


def get_icon_manager(theme: str = "dark") -> IconManager:
    global _global_icon_manager
    if _global_icon_manager is None:
        _global_icon_manager = IconManager(theme=theme)
    return _global_icon_manager
