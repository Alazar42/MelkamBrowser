from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Callable

import httpx

from .dom import Document


@dataclass
class FetchResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]


class Console:
    def log(self, *args: Any) -> None:
        print(*args)

    def warn(self, *args: Any) -> None:
        print("WARN:", *args)

    def error(self, *args: Any) -> None:
        print("ERROR:", *args)


class BrowserWindow:
    def __init__(self, page: Any) -> None:
        self.page = page


class PythonRuntime:
    def __init__(self, page: Any) -> None:
        self.page = page
        self.console = Console()

    def execute(self, code: str, document: Document) -> None:
        sandbox_builtins = {
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
        }

        globals_dict = {
            "__builtins__": sandbox_builtins,
            "document": document,
            "window": BrowserWindow(self.page),
            "console": self.console,
            "local_storage": self.page.local_storage,
            "session_storage": self.page.session_storage,
            "fetch": self.fetch,
            "set_timeout": self.set_timeout,
            "set_interval": self.set_interval,
        }
        exec(code, globals_dict, globals_dict)

    def fetch(self, url: str) -> FetchResponse:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        return FetchResponse(url=str(response.url), status_code=response.status_code, text=response.text, headers=dict(response.headers))

    def set_timeout(self, callback: Callable[[], None], delay_ms: int) -> threading.Timer:
        timer = threading.Timer(delay_ms / 1000.0, callback)
        timer.daemon = True
        timer.start()
        return timer

    def set_interval(self, callback: Callable[[], None], delay_ms: int) -> threading.Timer:
        def runner() -> None:
            callback()
            self.set_interval(callback, delay_ms)

        timer = threading.Timer(delay_ms / 1000.0, runner)
        timer.daemon = True
        timer.start()
        return timer