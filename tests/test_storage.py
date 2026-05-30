from __future__ import annotations

from pathlib import Path

from melkam_browser.core.page import BrowserPage
from melkam_browser.core.storage import BrowserDatabase, LocalStorage, SessionStorage


def test_local_storage_persists_across_instances(tmp_path: Path) -> None:
    database_path = tmp_path / "browser.sqlite3"

    storage = LocalStorage(database_path)
    storage["theme"] = "dark"
    storage["homepage"] = "https://example.com"

    reopened = LocalStorage(database_path)

    assert reopened["theme"] == "dark"
    assert reopened.get("homepage") == "https://example.com"
    assert "theme" in reopened
    assert reopened.items()["homepage"] == "https://example.com"


def test_session_storage_does_not_persist() -> None:
    first = SessionStorage()
    first["token"] = "abc123"

    second = SessionStorage()

    assert second.get("token") is None
    assert "token" not in second


def test_browser_page_records_history_visits(tmp_path: Path) -> None:
    page = BrowserPage(tmp_path)
    page.load_html("<html><head><title>Example</title></head><body><h1>Example</h1></body></html>", url="https://example.test/")

    history = page.database.search_history("example")

    assert history
    assert history[0].url == "https://example.test/"
    assert history[0].title == "Example"
    assert history[0].visit_count == 1


def test_browser_database_setting_round_trip(tmp_path: Path) -> None:
    database = BrowserDatabase(tmp_path / "browser.sqlite3")
    database.set_setting("search_engine", "https://duckduckgo.com/?q={query}")

    assert database.get_setting("search_engine") == "https://duckduckgo.com/?q={query}"