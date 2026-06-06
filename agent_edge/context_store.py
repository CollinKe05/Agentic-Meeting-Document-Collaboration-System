from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from . import task_store


THREAD_MAIN = "main"
FOCUS_MAIN = "MAIN"
KIND_TO_FOCUS = {
    "ocr": "OCR_ACTIVE",
    "meeting": "MEETING_ACTIVE",
    "document": "DOCUMENT_ACTIVE",
}

_lock = threading.RLock()
_initialized_paths: set[Path] = set()
_fts_available: dict[Path, bool] = {}


def ensure_schema(path: Path | None = None) -> None:
    db_path = path or task_store.get_db_path()
    task_store.ensure_schema(db_path)
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
                CREATE TABLE IF NOT EXISTS contexts (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS context_artifacts (
                    id TEXT PRIMARY KEY,
                    context_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(context_id) REFERENCES contexts(id)
                );
                CREATE TABLE IF NOT EXISTS context_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context_id TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    position_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(context_id) REFERENCES contexts(id)
                );
                CREATE TABLE IF NOT EXISTS active_contexts (
                    thread_id TEXT PRIMARY KEY,
                    focus_state TEXT NOT NULL,
                    context_id TEXT,
                    mode TEXT NOT NULL DEFAULT 'soft',
                    entered_reason TEXT NOT NULL DEFAULT '',
                    turns_since_used INTEGER NOT NULL DEFAULT 0,
                    expires_after_turns INTEGER NOT NULL DEFAULT 4,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_contexts_kind_updated ON contexts(kind, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_context_chunks_context ON context_chunks(context_id);
                """
            )
            _fts_available[resolved] = _ensure_fts(conn)
            conn.commit()
            _initialized_paths.add(resolved)
        finally:
            conn.close()


def create_context(
    *,
    kind: str,
    title: str,
    summary: str = "",
    source_path: str = "",
    status: str = "active",
    metadata: dict[str, Any] | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    ensure_schema()
    now = task_store.now_text()
    cid = context_id or _make_context_id(kind)
    with _lock, task_store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO contexts
                (id, kind, title, summary, source_path, status, metadata_json, created_at, updated_at)
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                COALESCE((SELECT created_at FROM contexts WHERE id = ?), ?),
                ?
            )
            """,
            (
                cid,
                kind,
                title,
                summary,
                source_path,
                status,
                _json_dumps(metadata or {}),
                cid,
                now,
                now,
            ),
        )
    return get_context(cid) or {}


def update_context(
    context_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    source_path: str | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    ensure_schema()
    fields = ["updated_at = ?"]
    values: list[Any] = [task_store.now_text()]
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if summary is not None:
        fields.append("summary = ?")
        values.append(summary)
    if source_path is not None:
        fields.append("source_path = ?")
        values.append(source_path)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if metadata is not None:
        fields.append("metadata_json = ?")
        values.append(_json_dumps(metadata))
    values.append(context_id)
    with _lock, task_store.connect() as conn:
        conn.execute(f"UPDATE contexts SET {', '.join(fields)} WHERE id = ?", values)
    return get_context(context_id)


def get_context(context_id: str, *, include_artifacts: bool = True, include_chunks: bool = False) -> dict[str, Any] | None:
    ensure_schema()
    with _lock, task_store.connect() as conn:
        row = conn.execute("SELECT * FROM contexts WHERE id = ?", (context_id,)).fetchone()
        if not row:
            return None
        item = _context_from_row(row)
        if include_artifacts:
            artifact_rows = conn.execute(
                "SELECT * FROM context_artifacts WHERE context_id = ? ORDER BY created_at ASC, id ASC",
                (context_id,),
            ).fetchall()
            item["artifacts"] = [_artifact_from_row(artifact) for artifact in artifact_rows]
        if include_chunks:
            chunk_rows = conn.execute(
                "SELECT * FROM context_chunks WHERE context_id = ? ORDER BY id ASC",
                (context_id,),
            ).fetchall()
            item["chunks"] = [_chunk_from_row(chunk) for chunk in chunk_rows]
    return item


def list_contexts(*, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_schema()
    query = "SELECT * FROM contexts"
    values: list[Any] = []
    if kind:
        query += " WHERE kind = ?"
        values.append(kind)
    query += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
    values.append(limit)
    with _lock, task_store.connect() as conn:
        rows = conn.execute(query, values).fetchall()
    return [_context_from_row(row) for row in rows]


def add_artifact(
    context_id: str,
    artifact_type: str,
    path: str,
    *,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    ensure_schema()
    now = task_store.now_text()
    aid = artifact_id or f"{context_id}:{artifact_type}:{uuid.uuid4().hex[:8]}"
    display_name = name or Path(path).name or artifact_type
    with _lock, task_store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO context_artifacts
                (id, context_id, artifact_type, path, name, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (aid, context_id, artifact_type, path, display_name, _json_dumps(metadata or {}), now),
        )
        conn.execute("UPDATE contexts SET updated_at = ? WHERE id = ?", (now, context_id))
        row = conn.execute("SELECT * FROM context_artifacts WHERE id = ?", (aid,)).fetchone()
    return _artifact_from_row(row)


def add_chunk(
    context_id: str,
    chunk_type: str,
    text: str,
    *,
    position: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    clean = str(text or "").strip()
    if not clean:
        return None
    ensure_schema()
    now = task_store.now_text()
    with _lock, task_store.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO context_chunks
                (context_id, chunk_type, text, position_json, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (context_id, chunk_type, clean, _json_dumps(position or {}), _json_dumps(metadata or {}), now),
        )
        chunk_id = int(cursor.lastrowid)
        if _is_fts_available(conn):
            conn.execute(
                "INSERT INTO context_chunks_fts (text, context_id, chunk_id) VALUES (?, ?, ?)",
                (clean, context_id, chunk_id),
            )
        conn.execute("UPDATE contexts SET updated_at = ? WHERE id = ?", (now, context_id))
        row = conn.execute("SELECT * FROM context_chunks WHERE id = ?", (chunk_id,)).fetchone()
    return _chunk_from_row(row)


def add_chunks(context_id: str, chunk_type: str, texts: list[str], *, metadata: dict[str, Any] | None = None) -> int:
    count = 0
    for index, text in enumerate(texts):
        if add_chunk(context_id, chunk_type, text, position={"index": index}, metadata=metadata):
            count += 1
    return count


def replace_chunks(context_id: str, chunk_type: str | None = None) -> None:
    ensure_schema()
    with _lock, task_store.connect() as conn:
        if chunk_type:
            ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM context_chunks WHERE context_id = ? AND chunk_type = ?",
                    (context_id, chunk_type),
                ).fetchall()
            ]
            conn.execute("DELETE FROM context_chunks WHERE context_id = ? AND chunk_type = ?", (context_id, chunk_type))
        else:
            ids = [int(row["id"]) for row in conn.execute("SELECT id FROM context_chunks WHERE context_id = ?", (context_id,)).fetchall()]
            conn.execute("DELETE FROM context_chunks WHERE context_id = ?", (context_id,))
        if ids and _is_fts_available(conn):
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM context_chunks_fts WHERE chunk_id IN ({placeholders})", ids)


def search_chunks(
    query: str,
    *,
    context_id: str | None = None,
    kind: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    ensure_schema()
    clean_query = _fts_query(query)
    with _lock, task_store.connect() as conn:
        if clean_query and _is_fts_available(conn):
            sql = """
                SELECT c.*, x.kind, x.title, x.summary, x.source_path
                FROM context_chunks_fts f
                JOIN context_chunks c ON c.id = f.chunk_id
                JOIN contexts x ON x.id = c.context_id
                WHERE context_chunks_fts MATCH ?
            """
            values: list[Any] = [clean_query]
            if context_id:
                sql += " AND c.context_id = ?"
                values.append(context_id)
            if kind:
                sql += " AND x.kind = ?"
                values.append(kind)
            sql += " ORDER BY bm25(context_chunks_fts) LIMIT ?"
            values.append(limit)
            rows = conn.execute(sql, values).fetchall()
        else:
            like_terms = [term for term in _tokenize(query)[:5] if term]
            sql = """
                SELECT c.*, x.kind, x.title, x.summary, x.source_path
                FROM context_chunks c
                JOIN contexts x ON x.id = c.context_id
                WHERE 1=1
            """
            values = []
            if context_id:
                sql += " AND c.context_id = ?"
                values.append(context_id)
            if kind:
                sql += " AND x.kind = ?"
                values.append(kind)
            if like_terms:
                sql += " AND (" + " OR ".join("c.text LIKE ?" for _ in like_terms) + ")"
                values.extend(f"%{term}%" for term in like_terms)
            sql += " ORDER BY c.id DESC LIMIT ?"
            values.append(limit)
            rows = conn.execute(sql, values).fetchall()
    return [_chunk_from_row(row, include_context=True) for row in rows]


def set_active_context(
    *,
    thread_id: str = THREAD_MAIN,
    focus_state: str,
    context_id: str | None,
    mode: str = "soft",
    entered_reason: str = "",
    expires_after_turns: int = 4,
) -> dict[str, Any]:
    ensure_schema()
    now = task_store.now_text()
    if focus_state == FOCUS_MAIN:
        context_id = None
        mode = "soft"
    with _lock, task_store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO active_contexts
                (thread_id, focus_state, context_id, mode, entered_reason, turns_since_used, expires_after_turns, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (thread_id, focus_state, context_id, mode, entered_reason, expires_after_turns, now),
        )
        row = conn.execute("SELECT * FROM active_contexts WHERE thread_id = ?", (thread_id,)).fetchone()
    return _active_from_row(row)


def activate_context(context_id: str, *, thread_id: str = THREAD_MAIN, reason: str = "manual") -> dict[str, Any]:
    context = get_context(context_id, include_artifacts=False)
    if not context:
        raise KeyError(context_id)
    return set_active_context(
        thread_id=thread_id,
        focus_state=focus_state_for_kind(str(context["kind"])),
        context_id=context_id,
        mode="soft",
        entered_reason=reason,
    )


def clear_active_context(*, thread_id: str = THREAD_MAIN, reason: str = "") -> dict[str, Any]:
    return set_active_context(thread_id=thread_id, focus_state=FOCUS_MAIN, context_id=None, mode="soft", entered_reason=reason)


def get_active_context(*, thread_id: str = THREAD_MAIN, include_context: bool = True) -> dict[str, Any]:
    ensure_schema()
    with _lock, task_store.connect() as conn:
        row = conn.execute("SELECT * FROM active_contexts WHERE thread_id = ?", (thread_id,)).fetchone()
    active = _active_from_row(row) if row else {
        "thread_id": thread_id,
        "focus_state": FOCUS_MAIN,
        "context_id": None,
        "mode": "soft",
        "entered_reason": "",
        "turns_since_used": 0,
        "expires_after_turns": 4,
        "updated_at": "",
    }
    if include_context and active.get("context_id"):
        active["context"] = get_context(str(active["context_id"]), include_artifacts=True)
    return active


def mark_active_used(*, thread_id: str = THREAD_MAIN) -> None:
    ensure_schema()
    with _lock, task_store.connect() as conn:
        conn.execute(
            "UPDATE active_contexts SET turns_since_used = 0, updated_at = ? WHERE thread_id = ?",
            (task_store.now_text(), thread_id),
        )


def age_active_context(*, thread_id: str = THREAD_MAIN) -> dict[str, Any]:
    ensure_schema()
    with _lock, task_store.connect() as conn:
        conn.execute(
            """
            UPDATE active_contexts
            SET turns_since_used = turns_since_used + 1, updated_at = ?
            WHERE thread_id = ? AND focus_state != ?
            """,
            (task_store.now_text(), thread_id, FOCUS_MAIN),
        )
    active = get_active_context(thread_id=thread_id, include_context=False)
    if (
        active.get("focus_state") != FOCUS_MAIN
        and active.get("mode") == "soft"
        and int(active.get("turns_since_used") or 0) >= int(active.get("expires_after_turns") or 4)
    ):
        return clear_active_context(thread_id=thread_id, reason="expired")
    return active


def focus_state_for_kind(kind: str) -> str:
    return KIND_TO_FOCUS.get(kind, FOCUS_MAIN)


def record_document_context(
    *,
    path: str,
    content: str,
    title: str | None = None,
    task_id: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    context_id = f"document_{_stable_suffix(path)}"
    chunks = split_text(content, max_chars=1400, overlap=120)
    summary = (content.strip().replace("\n", " ")[:300] if content else "")
    context = create_context(
        kind="document",
        title=title or f"{Path(path).name} 文档",
        summary=summary,
        source_path=path,
        metadata={"task_id": task_id} if task_id else {},
        context_id=context_id,
    )
    add_artifact(context["id"], "source", path, name=Path(path).name)
    replace_chunks(context["id"], "document_chunk")
    add_chunks(context["id"], "document_chunk", chunks, metadata={"path": path})
    if activate:
        set_active_context(focus_state="DOCUMENT_ACTIVE", context_id=context["id"], entered_reason="document_read")
    return get_context(context["id"]) or context


def split_text(text: str, *, max_chars: int = 1400, overlap: int = 120) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", clean) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = current[-overlap:] if overlap and len(current) > overlap else ""
        current = f"{current}\n\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append(current)
    if not chunks:
        for start in range(0, len(clean), max(1, max_chars - overlap)):
            chunks.append(clean[start : start + max_chars])
    return chunks


def _ensure_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS context_chunks_fts
            USING fts5(text, context_id UNINDEXED, chunk_id UNINDEXED)
            """
        )
        return True
    except sqlite3.OperationalError:
        return False


def _is_fts_available(conn: sqlite3.Connection) -> bool:
    resolved = task_store.get_db_path().resolve()
    available = _fts_available.get(resolved)
    if available is not None:
        return available
    try:
        conn.execute("SELECT 1 FROM context_chunks_fts LIMIT 1")
        _fts_available[resolved] = True
        return True
    except sqlite3.OperationalError:
        _fts_available[resolved] = False
        return False


def _context_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_loads(item.pop("metadata_json"), {})
    return item


def _artifact_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = _json_loads(item.pop("metadata_json"), {})
    return item


def _chunk_from_row(row: sqlite3.Row, *, include_context: bool = False) -> dict[str, Any]:
    item = dict(row)
    item["position"] = _json_loads(item.pop("position_json"), {})
    item["metadata"] = _json_loads(item.pop("metadata_json"), {})
    if include_context:
        item["context"] = {
            "id": item.get("context_id"),
            "kind": item.pop("kind", ""),
            "title": item.pop("title", ""),
            "summary": item.pop("summary", ""),
            "source_path": item.pop("source_path", ""),
        }
    return item


def _active_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _make_context_id(kind: str) -> str:
    return f"{kind}_{uuid.uuid4().hex[:12]}"


def _stable_suffix(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if len(text) > 48:
        text = text[-48:]
    return text or uuid.uuid4().hex[:8]


def _tokenize(query: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", query)


def _fts_query(query: str) -> str:
    tokens = _tokenize(query)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens[:8])
