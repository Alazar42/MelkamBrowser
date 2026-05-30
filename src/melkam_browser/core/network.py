from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
from urllib.parse import urlparse

import httpx


@dataclass
class Resource:
    url: str
    content_type: str
    text: str
    bytes_data: bytes | None = None


class HttpClient:
    def get(self, url: str) -> Resource:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        return Resource(url=str(response.url), content_type=response.headers.get("content-type", "text/plain"), text=response.text, bytes_data=response.content)


class ResourceLoader:
    def __init__(self) -> None:
        self.http = HttpClient()

    def load(self, target: str) -> Resource:
        stripped = target.strip()
        if stripped.startswith("<"):
            return Resource(url="about:blank", content_type="text/html", text=stripped)

        # Treat drive-letter absolute paths as files on Windows (e.g. C:\site\index.html).
        if re.match(r"^[a-zA-Z]:[\\/]", stripped):
            path = Path(stripped)
            if path.exists():
                suffix = path.suffix.lower()
                content_type = "text/html" if suffix in {".html", ".htm"} else "text/plain"
                return Resource(url=path.resolve().as_uri(), content_type=content_type, text=path.read_text(encoding="utf-8"))

        if stripped == "about:blank":
            return Resource(url="about:blank", content_type="text/html", text="<html><body></body></html>")

        if stripped.startswith("data:"):
            return Resource(url="about:blank", content_type="text/html", text=stripped)

        parsed = urlparse(stripped)
        if parsed.scheme in {"http", "https"}:
            return self.http.get(stripped)

        if parsed.scheme and parsed.scheme not in {"file"}:
            return Resource(url=stripped, content_type="text/plain", text=escape(stripped))

        path = Path(stripped)
        if path.exists():
            suffix = path.suffix.lower()
            content_type = "text/html" if suffix in {".html", ".htm"} else "text/plain"
            return Resource(url=path.resolve().as_uri(), content_type=content_type, text=path.read_text(encoding="utf-8"))

        if "." in stripped and " " not in stripped:
            return self.http.get(f"https://{stripped}")

        return Resource(url="about:blank", content_type="text/html", text=f"<html><body><pre>{escape(stripped)}</pre></body></html>")