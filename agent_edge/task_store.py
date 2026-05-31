from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .paths import PROJECT_ROOT


DEFAULT_DB_PATH = PROJECT_ROOT / ".runtime" / "agent_tasks.sqlite3"
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}

_lock = threading.RLock()
_initialized_paths: set[Path] = set()


def get_db_path() -> Path:
    return Path(os.environ.get("AGENT_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = get_db_path()
    ensure_schema(path)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema(path: Path | None = None) -> None:
    db_path = path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = db_path.resolve()
    with _lock:
        if resolved in _initialized_paths:
            return
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                """
            )
            conn.commit()
            _initialized_paths.add(resolved)
        finally:
            conn.close()


def reset_initialized_for_tests() -> None:
    with _lock:
        _initialized_paths.clear()


def create_task(task_id: str, *, prompt: str, backend: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
    created_at = now_text()
    attachments_json = json.dumps(attachments, ensure_ascii=False)
    with _lock, connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, created_at, updated_at, prompt, status, backend, attachments_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, created_at, created_at, prompt, "queued", backend, attachments_json),
        )
    return get_task(task_id) or {}


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    result: str | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [now_text()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if result is not None:
        fields.append("result = ?")
        values.append(result)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    values.append(task_id)

    with _lock, connect() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def list_tasks(*, limit: int = 50) -> list[dict[str, Any]]:
    with _lock, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def add_event(
    task_id: str,
    event_type: str,
    title: str,
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = now_text()
    payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
    with _lock, connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO task_events (task_id, created_at, type, title, message, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, created_at, event_type, title, message, payload_json),
        )
        event_id = int(cursor.lastrowid)
    return get_event(event_id) or {}


def get_event(event_id: int) -> dict[str, Any] | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM task_events WHERE id = ?", (event_id,)).fetchone()
    return _event_from_row(row) if row else None


def list_events(task_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    with _lock, connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM task_events
            WHERE task_id = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (task_id, after_id, limit),
        ).fetchall()
    return [_event_from_row(row) for row in rows]


def record_artifact(
    artifact_id: str,
    *,
    task_id: str | None,
    kind: str,
    path: str,
    name: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = now_text()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)
    with _lock, connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO artifacts
                (id, task_id, created_at, kind, path, name, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (artifact_id, task_id, created_at, kind, path, name, metadata_json),
        )
    return get_artifact(artifact_id) or {}


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return _artifact_from_row(row) if row else None


def latest_artifact(*, kind: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM artifacts"
    values: list[Any] = []
    if kind:
        query += " WHERE kind = ?"
        values.append(kind)
    query += " ORDER BY created_at DESC, id DESC LIMIT 1"
    with _lock, connect() as conn:
        row = conn.execute(query, values).fetchone()
    return _artifact_from_row(row) if row else None


def _task_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["attachments"] = _json_loads(item.pop("attachments_json"), [])
    return item


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = _json_loads(item.pop("payload_json"), {})
    return item


def _artifact_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_loads(item.pop("metadata_json"), {})
    return item


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
