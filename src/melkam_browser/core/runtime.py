from __future__ import annotations

import asyncio
from dataclasses import dataclass
import sys
import threading
import traceback
from typing import Any, Callable, Optional

import httpx

from .dom import Document


@dataclass
class FetchResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]


@dataclass
class RuntimeErrorRecord:
    message: str
    file: str
    line: int
    source: str
    traceback_text: str
    exception_type: str


class Console:
    def __init__(self, context: RuntimeContext) -> None:
        self.context = context

    def log(self, *args: Any) -> None:
        message = " ".join(str(arg) for arg in args)
        self.context.log_message("log", message)

    def warn(self, *args: Any) -> None:
        message = " ".join(str(arg) for arg in args)
        self.context.log_message("warn", message)

    def error(self, *args: Any) -> None:
        message = " ".join(str(arg) for arg in args)
        self.context.log_message("error", message)


class BrowserWindow:
    def __init__(self, page: Any) -> None:
        self.page = page


class RuntimeContext:
    """Per-tab isolated Python execution context with proper lifecycle management."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.console = Console(self)
        self._timers: dict[int, asyncio.Task] = {}
        self._timer_id_counter = 0
        self._lock = threading.RLock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._running = False
        self._errors: list[RuntimeErrorRecord] = []
        self._execution_task: Optional[asyncio.Task] = None
        self._start_event_loop()

    def _start_event_loop(self) -> None:
        """Start a dedicated event loop for this context."""
        def _loop_runner() -> None:
            try:
                self._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._event_loop)
                self._running = True
                self._event_loop.run_forever()
            finally:
                self._running = False
                if self._event_loop:
                    pending = asyncio.all_tasks(self._event_loop)
                    for task in pending:
                        task.cancel()
                    self._event_loop.stop()

        self._loop_thread = threading.Thread(target=_loop_runner, daemon=True)
        self._loop_thread.start()
        
        while self._event_loop is None and self._loop_thread.is_alive():
            threading.Event().wait(0.01)

    def execute(self, code: str, document: Document) -> None:
        """Execute Python code with proper error handling and isolation."""
        print(f"[PY] execute start bytes={len(code)}", flush=True)
        try:
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
                "__name__": "__main__",
                "__doc__": None,
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
        except Exception as exc:
            self._capture_error(exc, code)
        finally:
            print("[PY] execute end", flush=True)

    def _capture_error(self, exc: Exception, source_code: str) -> None:
        """Capture and record execution errors with full context."""
        tb = sys.exc_info()[2]
        tb_text = "".join(traceback.format_tb(tb))
        tb_lines = tb_text.split("\n")
        
        line_num = 1
        if tb and tb.tb_lineno:
            line_num = tb.tb_lineno

        source_lines = source_code.split("\n")
        line_content = source_lines[line_num - 1] if 0 < line_num <= len(source_lines) else ""

        error_record = RuntimeErrorRecord(
            message=str(exc),
            file="<script>",
            line=line_num,
            source=line_content.strip(),
            traceback_text=tb_text,
            exception_type=type(exc).__name__,
        )
        
        with self._lock:
            self._errors.append(error_record)
        
        self.console.error(f"{error_record.exception_type}: {error_record.message}")

    def log_message(self, level: str, message: str) -> None:
        """Callback for console logging."""
        if self.page and hasattr(self.page, "_on_console"):
            self.page._on_console(level, message)

    def fetch(self, url: str) -> FetchResponse:
        """Synchronous fetch for backwards compatibility."""
        try:
            response = httpx.get(url, follow_redirects=True, timeout=10.0)
            return FetchResponse(
                url=str(response.url),
                status_code=response.status_code,
                text=response.text,
                headers=dict(response.headers),
            )
        except Exception as exc:
            raise RuntimeError(f"Fetch failed: {exc}") from exc

    async def fetch_async(self, url: str) -> FetchResponse:
        """Async fetch for modern code."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True, timeout=10.0)
            return FetchResponse(
                url=str(response.url),
                status_code=response.status_code,
                text=response.text,
                headers=dict(response.headers),
            )
        except Exception as exc:
            raise RuntimeError(f"Fetch failed: {exc}") from exc

    def set_timeout(self, callback: Callable[[], None], delay_ms: int) -> int:
        """Schedule callback after delay with proper cleanup."""
        timer_id = self._timer_id_counter
        self._timer_id_counter += 1

        async def _timeout_task() -> None:
            try:
                await asyncio.sleep(delay_ms / 1000.0)
                callback()
            except Exception as exc:
                self._capture_error(exc, "")
            finally:
                with self._lock:
                    self._timers.pop(timer_id, None)

        if self._event_loop and self._running:
            task = asyncio.run_coroutine_threadsafe(_timeout_task(), self._event_loop)
            with self._lock:
                self._timers[timer_id] = task

        return timer_id

    def set_interval(self, callback: Callable[[], None], delay_ms: int) -> int:
        """Schedule repeating callback with proper cleanup."""
        timer_id = self._timer_id_counter
        self._timer_id_counter += 1

        async def _interval_task() -> None:
            try:
                while timer_id in self._timers:
                    await asyncio.sleep(delay_ms / 1000.0)
                    if timer_id in self._timers:
                        callback()
            except Exception as exc:
                self._capture_error(exc, "")
            finally:
                with self._lock:
                    self._timers.pop(timer_id, None)

        if self._event_loop and self._running:
            task = asyncio.run_coroutine_threadsafe(_interval_task(), self._event_loop)
            with self._lock:
                self._timers[timer_id] = task

        return timer_id

    def clear_timeout(self, timer_id: int) -> None:
        """Cancel a scheduled timeout."""
        with self._lock:
            task = self._timers.pop(timer_id, None)
            if task:
                task.cancel()

    def clear_interval(self, timer_id: int) -> None:
        """Cancel a scheduled interval."""
        with self._lock:
            task = self._timers.pop(timer_id, None)
            if task:
                task.cancel()

    def cleanup(self) -> None:
        """Clean up all resources and stop the event loop."""
        with self._lock:
            for task in self._timers.values():
                task.cancel()
            self._timers.clear()

        if self._event_loop and self._running:
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)

    def get_errors(self) -> list[RuntimeErrorRecord]:
        """Retrieve all recorded runtime errors."""
        with self._lock:
            return list(self._errors)

    def clear_errors(self) -> None:
        """Clear error log."""
        with self._lock:
            self._errors.clear()


class PythonRuntime:
    """Wrapper for backwards compatibility."""

    def __init__(self, page: Any) -> None:
        self.context = RuntimeContext(page)

    def execute(self, code: str, document: Document) -> None:
        self.context.execute(code, document)

    def cleanup(self) -> None:
        self.context.cleanup()
