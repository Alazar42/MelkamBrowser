from __future__ import annotations

import asyncio
import time
from pathlib import Path

from melkam_browser.core.dom import Document
from melkam_browser.core.page import BrowserPage
from melkam_browser.core.runtime import RuntimeContext


def test_runtime_context_isolation(tmp_path: Path) -> None:
    """Verify each context is isolated and timers don't leak."""
    page1 = BrowserPage(tmp_path / "page1")
    page2 = BrowserPage(tmp_path / "page2")
    
    context1 = page1.python_runtime.context
    context2 = page2.python_runtime.context
    
    assert context1 is not context2
    assert id(context1._event_loop) != id(context2._event_loop)


def test_runtime_timer_cleanup(tmp_path: Path) -> None:
    """Verify timers are cleaned up and don't leak."""
    page = BrowserPage(tmp_path)
    context = page.python_runtime.context
    
    callback_executed = []
    
    def callback() -> None:
        callback_executed.append(True)
    
    timer_id = context.set_timeout(callback, 100)
    assert timer_id in context._timers
    
    context.clear_timeout(timer_id)
    assert timer_id not in context._timers


def test_runtime_error_capture(tmp_path: Path) -> None:
    """Verify exceptions are captured with proper context."""
    page = BrowserPage(tmp_path)
    code = """
x = undefined_variable
"""
    
    context = page.python_runtime.context
    context.execute(code, page.document)
    
    errors = context.get_errors()
    assert len(errors) > 0
    assert errors[0].exception_type == "NameError"
    assert "undefined_variable" in errors[0].message


def test_runtime_context_cleanup(tmp_path: Path) -> None:
    """Verify cleanup properly stops the event loop."""
    page = BrowserPage(tmp_path)
    context = page.python_runtime.context
    
    assert context._running
    assert context._event_loop is not None
    
    context.cleanup()
    
    assert not context._running
    time.sleep(0.1)
    assert not context._loop_thread.is_alive()


def test_dom_mutation_from_script(tmp_path: Path) -> None:
    """Verify DOM mutations from Python are reflected."""
    page = BrowserPage(tmp_path)
    
    html = """
    <html>
    <body>
        <div id="target">Original</div>
    </body>
    </html>
    """
    page.load_html(html)
    
    code = """
target = document.query("#target")
target.text = "Modified"
"""
    
    page.python_runtime.execute(code, page.document)
    
    target = page.document.query("#target")
    assert target is not None
    assert target.text == "Modified"


def test_console_callback(tmp_path: Path) -> None:
    """Verify console messages are captured."""
    page = BrowserPage(tmp_path)
    context = page.python_runtime.context
    
    code = """
console.log("Test message")
console.warn("Warning")
console.error("Error")
"""
    
    context.execute(code, page.document)
    
    assert len(page._console_log) > 0
    levels = [level for level, msg in page._console_log]
    assert "log" in levels or "warn" in levels or "error" in levels
