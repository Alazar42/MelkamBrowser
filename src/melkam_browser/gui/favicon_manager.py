from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PySide6.QtCore import QObject, Signal


class FaviconManager(QObject):
    favicon_ready = Signal(str, str)  # host, path

    def __init__(self, storage_root: Path) -> None:
        super().__init__()
        self.storage_root = Path(storage_root) / "favicons"
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _local_path_for_host(self, host: str) -> str:
        return str(self.storage_root / f"{host}.png")

    def fetch(self, page_url: str) -> None:
        parsed = urlparse(page_url)
        host = parsed.netloc or parsed.path

        dest = self._local_path_for_host(host)
        if Path(dest).exists():
            self.favicon_ready.emit(host, dest)
            return

        def worker() -> None:
            try:
                # Simple strategy: try /favicon.ico first
                base = f"{parsed.scheme}://{parsed.netloc}"
                candidate = f"{base}/favicon.ico"
                r = httpx.get(candidate, follow_redirects=True, timeout=10.0)
                if r.status_code == 200 and r.content:
                    with open(dest, "wb") as f:
                        f.write(r.content)
                    self.favicon_ready.emit(host, dest)
                    return
            except Exception:
                pass
            # fallback: no favicon
            self.favicon_ready.emit(host, "")

        threading.Thread(target=worker, daemon=True).start()
