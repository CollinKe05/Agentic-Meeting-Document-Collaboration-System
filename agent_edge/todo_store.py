from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .paths import PROJECT_ROOT


DEFAULT_DB_PATH = PROJECT_ROOT / "todo_rdk" / "data" / "tasks.db"
VALID_PRIORITIES = {"高", "中", "低"}

_lock = threading.RLock()
_initialized_paths: set[Path] = set()


def get_db_path() -> Path:
    return Path(os.environ.get("AGENT_TODO_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_schema()
    conn = sqlite3.connect(get_db_path(), timeout=30)
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
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            if not _table_exists(conn, "tasks"):
                _create_schema(conn)
            elif not _has_valid_priority_schema(conn):
                _backup_db(db_path)
                _migrate_priority_schema(conn)
            else:
                _create_updated_at_trigger(conn)
            conn.commit()
            _initialized_paths.add(resolved)
        finally:
            conn.close()


def reset_initialized_for_tests() -> None:
    with _lock:
        _initialized_paths.clear()


def list_tasks(*, limit: int = 200, include_completed: bool = True) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    where = "" if include_completed else "WHERE completed = 0"
    with _lock, connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM tasks
            {where}
            ORDER BY
                completed ASC,
                CASE priority
                    WHEN '高' THEN 1
                    WHEN '中' THEN 2
                    WHEN '低' THEN 3
                    ELSE 4
                END ASC,
                CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END ASC,
                due_date ASC,
                created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def get_task(task_id: int | str) -> dict[str, Any] | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (_coerce_task_id(task_id),)).fetchone()
    return _task_from_row(row) if row else None


def add_task(task_data: dict[str, Any]) -> dict[str, Any]:
    data = _normalize_task_payload(task_data, require_title=True)
    with _lock, connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, description, priority, completed, category, due_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"],
                data.get("description"),
                data["priority"],
                int(bool(data.get("completed", False))),
                data.get("category"),
                data.get("due_date"),
            ),
        )
        task_id = int(cursor.lastrowid)
    task = get_task(task_id)
    if not task:
        raise RuntimeError("日程已写入，但无法读取新增记录")
    return task


def update_task(task_id: int | str, task_data: dict[str, Any]) -> dict[str, Any] | None:
    _coerce_task_id(task_id)
    data = _normalize_task_payload(task_data, require_title=False)
    allowed = ["title", "description", "priority", "completed", "category", "due_date"]
    fields: list[str] = []
    values: list[Any] = []

    for key in allowed:
        if key not in data:
            continue
        value = data[key]
        if key == "completed":
            value = int(bool(value))
        fields.append(f"{key} = ?")
        values.append(value)

    if not fields:
        raise ValueError("没有可更新的日程字段")

    values.append(_coerce_task_id(task_id))
    with _lock, connect() as conn:
        cursor = conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
        if cursor.rowcount <= 0:
            return None
    return get_task(task_id)


def delete_task(task_id: int | str) -> bool:
    with _lock, connect() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (_coerce_task_id(task_id),))
        return cursor.rowcount > 0


def find_tasks(query: str, *, include_completed: bool = True, limit: int = 10) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    where_completed = "" if include_completed else "AND completed = 0"
    like = f"%{query}%"
    with _lock, connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM tasks
            WHERE (title = ? OR title LIKE ? OR category LIKE ? OR description LIKE ?)
            {where_completed}
            ORDER BY
                CASE WHEN title = ? THEN 0 ELSE 1 END ASC,
                completed ASC,
                due_date ASC,
                created_at DESC
            LIMIT ?
            """,
            (query, like, like, like, query, max(1, min(int(limit), 50))),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def apply_instruction(instruction: str, *, now: datetime | None = None) -> dict[str, Any]:
    text = " ".join(str(instruction or "").split())
    if not text:
        return {"ok": False, "error": "日程指令不能为空"}

    intent = _detect_intent(text)
    if intent == "list":
        return {"ok": True, "action": "list", "tasks": list_tasks(limit=50)}

    if intent == "add":
        due_date = _parse_due_datetime(text, now=now)
        if not due_date:
            return {"ok": False, "error": "请补充明确的日期和时间，例如：明天下午3点。"}
        title = _extract_title(text, intent)
        if not title:
            return {"ok": False, "error": "请补充日程标题，例如：明天下午3点开会。"}
        task = add_task(
            {
                "title": title,
                "description": "",
                "priority": _infer_priority(text),
                "category": _infer_category(text, title),
                "due_date": due_date,
            }
        )
        return {"ok": True, "action": "add", "task": task, "message": f"已添加日程：{task['title']}，时间 {task['due_date']}。"}

    query = _extract_title(text, intent)
    if not query:
        return {"ok": False, "error": "请说明要操作哪条日程。"}

    matches = _select_matches(query, include_completed=intent != "complete")
    if len(matches) != 1:
        return _ambiguous_match_result(query, matches)

    task = matches[0]
    if intent == "complete":
        updated = update_task(task["id"], {"completed": True})
        return {"ok": True, "action": "complete", "task": updated, "message": f"已完成日程：{task['title']}。"}

    if intent == "delete":
        delete_task(task["id"])
        return {"ok": True, "action": "delete", "task": task, "message": f"已删除日程：{task['title']}。"}

    if intent == "update":
        due_date = _parse_due_datetime(text, now=now)
        if not due_date:
            return {"ok": False, "error": "请说明新的日期和时间，例如：改到后天下午4点。"}
        updated = update_task(task["id"], {"due_date": due_date})
        return {"ok": True, "action": "update", "task": updated, "message": f"已更新日程：{task['title']}，新时间 {due_date}。"}

    return {"ok": False, "error": "无法识别日程操作，请换一种说法。"}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _has_valid_priority_schema(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'").fetchone()
    sql = str(row["sql"] if row else "")
    return all(priority in sql for priority in VALID_PRIORITIES)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT CHECK(priority IN ('高', '中', '低')) DEFAULT '中',
            completed BOOLEAN DEFAULT 0,
            category TEXT,
            due_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _create_updated_at_trigger(conn)


def _create_updated_at_trigger(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS update_task_updated_at
        AFTER UPDATE ON tasks
        FOR EACH ROW
        WHEN OLD.updated_at = NEW.updated_at
        BEGIN
            UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """
    )


def _backup_db(db_path: Path) -> None:
    if not db_path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup_path)


def _migrate_priority_schema(conn: sqlite3.Connection) -> None:
    legacy = f"tasks_legacy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    conn.execute("DROP TRIGGER IF EXISTS update_task_updated_at")
    conn.execute(f"ALTER TABLE tasks RENAME TO {legacy}")
    _create_schema(conn)
    conn.execute(
        f"""
        INSERT INTO tasks (id, title, description, priority, completed, category, due_date, created_at, updated_at)
        SELECT
            id,
            title,
            description,
            CASE WHEN priority IN ('高', '中', '低') THEN priority ELSE '中' END,
            CASE WHEN completed IN (1, '1', 'true', 'True') THEN 1 ELSE 0 END,
            category,
            due_date,
            COALESCE(created_at, CURRENT_TIMESTAMP),
            COALESCE(updated_at, CURRENT_TIMESTAMP)
        FROM {legacy}
        """
    )
    conn.execute(f"DROP TABLE {legacy}")


def _normalize_task_payload(task_data: dict[str, Any], *, require_title: bool) -> dict[str, Any]:
    if not isinstance(task_data, dict):
        raise ValueError("日程数据必须是 JSON object")

    data: dict[str, Any] = {}
    if "title" in task_data or require_title:
        title = str(task_data.get("title", "")).strip()
        if not title:
            raise ValueError("日程标题不能为空")
        data["title"] = title[:120]

    if "description" in task_data:
        data["description"] = _optional_text(task_data.get("description"))
    if "category" in task_data:
        data["category"] = _optional_text(task_data.get("category"))
    if "completed" in task_data:
        data["completed"] = bool(task_data.get("completed"))
    if "priority" in task_data or require_title:
        data["priority"] = _normalize_priority(task_data.get("priority", "中"))
    if "due_date" in task_data:
        data["due_date"] = normalize_due_date(task_data.get("due_date"))

    return data


def normalize_due_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text):
        return f"{text}:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return text
    raise ValueError("due_date 必须是 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS")


def _normalize_priority(value: Any) -> str:
    priority = str(value or "中").strip()
    return priority if priority in VALID_PRIORITIES else "中"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _coerce_task_id(task_id: int | str) -> int:
    try:
        value = int(task_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("日程 id 必须是整数") from exc
    if value <= 0:
        raise ValueError("日程 id 必须大于 0")
    return value


def _task_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["completed"] = bool(item.get("completed"))
    item["priority"] = _normalize_priority(item.get("priority"))
    return item


def _detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(word in text for word in ("列出", "查看", "看看", "有哪些")) and any(word in text for word in ("日程", "待办", "任务")):
        return "list"
    if any(word in text for word in ("删除", "删掉", "移除", "取消")):
        return "delete"
    if any(word in text for word in ("完成", "做完", "办完", "标记完成")):
        return "complete"
    if any(word in text for word in ("改到", "改为", "调整到", "延期到", "提前到", "修改", "更新")):
        return "update"
    if any(word in lowered for word in ("todo", "schedule")) or any(word in text for word in ("提醒", "添加", "新增", "安排", "创建", "待办", "日程", "任务")):
        return "add"
    return "unknown"


def _parse_due_datetime(text: str, *, now: datetime | None = None) -> str | None:
    base = now or datetime.now()
    date_part = _parse_date(text, base)
    time_part = _parse_time(text)
    if not date_part or not time_part:
        return None
    combined = datetime(date_part.year, date_part.month, date_part.day, time_part[0], time_part[1], 0)
    return combined.strftime("%Y-%m-%d %H:%M:%S")


def _parse_date(text: str, base: datetime) -> datetime | None:
    if "大后天" in text:
        return base + timedelta(days=3)
    if "后天" in text:
        return base + timedelta(days=2)
    if "明天" in text:
        return base + timedelta(days=1)
    if "今天" in text:
        return base

    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = re.search(r"(?<!\d)(\d{1,2})[-/月](\d{1,2})(?:日|号)?", text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = base.year
        candidate = _safe_date(year, month, day)
        if candidate and candidate.date() < base.date():
            candidate = _safe_date(year + 1, month, day)
        return candidate

    weekday_match = re.search(r"(下周|下星期|下礼拜)?(?:周|星期|礼拜)([一二三四五六日天])", text)
    if weekday_match:
        target = "一二三四五六日天".index(weekday_match.group(2))
        if target == 7:
            target = 6
        current = base.weekday()
        if weekday_match.group(1):
            days_until_next_monday = 7 - current
            return base + timedelta(days=days_until_next_monday + target)
        delta = (target - current) % 7
        return base + timedelta(days=delta)

    return None


def _safe_date(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _parse_time(text: str) -> tuple[int, int] | None:
    marker = _time_marker(text)
    match = re.search(r"(\d{1,2})[:：](\d{1,2})", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return _normalize_hour_minute(hour, minute, marker)

    match = re.search(r"([零〇一二两三四五六七八九十\d]{1,3})点半", text)
    if match:
        hour = _parse_chinese_number(match.group(1))
        return _normalize_hour_minute(hour, 30, marker)

    match = re.search(r"([零〇一二两三四五六七八九十\d]{1,3})点(?:([零〇一二两三四五六七八九十\d]{1,3})分?)?", text)
    if match:
        hour = _parse_chinese_number(match.group(1))
        minute = _parse_chinese_number(match.group(2)) if match.group(2) else 0
        return _normalize_hour_minute(hour, minute, marker)

    if "中午" in text:
        return (12, 0)

    return None


def _time_marker(text: str) -> str:
    if any(word in text for word in ("下午", "晚上", "傍晚", "今晚", "晚间")):
        return "pm"
    if any(word in text for word in ("凌晨",)):
        return "late_night"
    if any(word in text for word in ("上午", "早上", "早晨")):
        return "am"
    return ""


def _normalize_hour_minute(hour: int | None, minute: int | None, marker: str) -> tuple[int, int] | None:
    if hour is None or minute is None or minute < 0 or minute > 59:
        return None
    if marker == "pm" and 1 <= hour < 12:
        hour += 12
    if marker == "late_night" and hour == 12:
        hour = 0
    if hour < 0 or hour > 23:
        return None
    return (hour, minute)


def _parse_chinese_number(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return digits.get(value)


def _extract_title(text: str, intent: str) -> str:
    if intent == "update":
        match = re.search(r"把(.+?)(?:改到|改为|调整到|延期到|提前到|修改|更新)", text)
        if match:
            return _clean_title(match.group(1))
    cleaned = _strip_datetime_terms(text)
    if intent == "add":
        cleaned = re.sub(r"^(请|帮我|麻烦|提醒我|提醒|添加|新增|安排|创建|加一个|加一条|新建)", "", cleaned)
    elif intent == "complete":
        cleaned = re.sub(r"^(请|帮我|麻烦|完成|做完|办完|标记完成)", "", cleaned)
    elif intent == "delete":
        cleaned = re.sub(r"^(请|帮我|麻烦|删除|删掉|移除|取消)", "", cleaned)
    return _clean_title(cleaned)


def _strip_datetime_terms(text: str) -> str:
    patterns = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日|号)?",
        r"(?<!\d)\d{1,2}[-/月]\d{1,2}(?:日|号)?",
        r"(?:下周|下星期|下礼拜)?(?:周|星期|礼拜)[一二三四五六日天]",
        r"大后天|后天|明天|今天",
        r"上午|下午|晚上|傍晚|今晚|早上|早晨|凌晨|中午",
        r"\d{1,2}[:：]\d{1,2}",
        r"[零〇一二两三四五六七八九十\d]{1,3}点半",
        r"[零〇一二两三四五六七八九十\d]{1,3}点(?:[零〇一二两三四五六七八九十\d]{1,3}分?)?",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = re.sub(r"(改到|改为|调整到|延期到|提前到)", " ", cleaned)
    return cleaned


def _clean_title(value: str) -> str:
    text = value.strip(" ，。；;,.!！?？：:")
    text = re.sub(r"^(一个|一条|这个|这条|的)", "", text)
    text = re.sub(r"(的)?(日程|待办|任务|提醒)$", "", text)
    text = text.strip(" ，。；;,.!！?？：:")
    return text[:120]


def _infer_priority(text: str) -> str:
    if any(word in text for word in ("紧急", "重要", "高优先级", "优先级高")):
        return "高"
    if any(word in text for word in ("低优先级", "不急", "优先级低")):
        return "低"
    return "中"


def _infer_category(text: str, title: str) -> str:
    combined = f"{text} {title}"
    if "会议" in combined or "开会" in combined:
        return "会议"
    for category in ("会议", "工作", "学习", "生活", "日程"):
        if category in combined:
            return category
    return "日程"


def _select_matches(query: str, *, include_completed: bool) -> list[dict[str, Any]]:
    matches = find_tasks(query, include_completed=include_completed, limit=10)
    exact = [task for task in matches if task["title"] == query]
    return exact if exact else matches


def _ambiguous_match_result(query: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    if not matches:
        return {"ok": False, "error": f"没有找到匹配“{query}”的日程。"}
    return {
        "ok": False,
        "error": f"找到多条匹配“{query}”的日程，请说得更具体。",
        "candidates": matches,
    }
