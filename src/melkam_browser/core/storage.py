from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock


@dataclass(frozen=True)
class HistoryEntry:
    url: str
    title: str
    resource_type: str
    visit_count: int
    first_visited_at: str
    last_visited_at: str


class BrowserDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS kv_store (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(namespace, key)
                );

                CREATE TABLE IF NOT EXISTS history (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    visit_count INTEGER NOT NULL,
                    first_visited_at TEXT NOT NULL,
                    last_visited_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    folder TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    bytes_received INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "BrowserDatabase":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_value(self, namespace: str, key: str, value: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO kv_store(namespace, key, value)
                VALUES(?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value
                """,
                (namespace, key, value),
            )

    def get_value(self, namespace: str, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM kv_store WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
        return default if row is None else str(row[0])

    def delete_value(self, namespace: str, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM kv_store WHERE namespace = ? AND key = ?",
                (namespace, key),
            )

    def list_values(self, namespace: str) -> dict[str, str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT key, value FROM kv_store WHERE namespace = ? ORDER BY key",
                (namespace,),
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def record_visit(self, url: str, title: str, resource_type: str) -> None:
        timestamp = self._timestamp()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT visit_count FROM history WHERE url = ?",
                (url,),
            ).fetchone()
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO history(url, title, resource_type, visit_count, first_visited_at, last_visited_at)
                    VALUES(?, ?, ?, 1, ?, ?)
                    """,
                    (url, title, resource_type, timestamp, timestamp),
                )
                return

            self._connection.execute(
                """
                UPDATE history
                SET title = ?, resource_type = ?, visit_count = visit_count + 1, last_visited_at = ?
                WHERE url = ?
                """,
                (title, resource_type, timestamp, url),
            )

    def search_history(self, query: str = "", limit: int = 100) -> list[HistoryEntry]:
        normalized = f"%{query.strip().lower()}%" if query.strip() else "%"
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT url, title, resource_type, visit_count, first_visited_at, last_visited_at
                FROM history
                WHERE LOWER(url) LIKE ? OR LOWER(title) LIKE ?
                ORDER BY last_visited_at DESC
                LIMIT ?
                """,
                (normalized, normalized, limit),
            ).fetchall()
        return [HistoryEntry(**dict(row)) for row in rows]

    def set_setting(self, key: str, value: str) -> None:
        timestamp = self._timestamp()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, timestamp),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return default if row is None else str(row[0])


class PersistentStorage:
    def __init__(self, database: BrowserDatabase, namespace: str) -> None:
        self.database = database
        self.namespace = namespace

    def __getitem__(self, key: str) -> str:
        value = self.database.get_value(self.namespace, key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: str) -> None:
        self.database.set_value(self.namespace, key, value)

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        self.database.delete_value(self.namespace, key)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.database.get_value(self.namespace, key, default)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self.database.get_value(self.namespace, key) is not None

    def items(self) -> dict[str, str]:
        return self.database.list_values(self.namespace)


class LocalStorage(PersistentStorage):
    def __init__(self, database: BrowserDatabase | Path) -> None:
        if isinstance(database, Path):
            database = BrowserDatabase(database)
        super().__init__(database, "local_storage")


class SessionStorage:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def clear(self) -> None:
        self._data.clear()