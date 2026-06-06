from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import context_store, todo_store
from .meeting_formatter import format_meeting_minutes
from .ocr_memory import read_latest_ocr_result
from .ocr_pc_tool import parse_document_with_ocr_pc
from .paths import (
    SKILLS_DIR,
    WORKSPACE_DIR,
    read_limited_text,
    safe_child_path,
    write_limited_text,
)


def json_observation(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _maybe_record_document_context(rel_path: str, content: str, *, task_id: str | None) -> None:
    suffix = Path(rel_path).suffix.lower()
    code_like = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".css",
        ".html",
        ".sh",
        ".ps1",
        ".bat",
        ".cmd",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".json",
        ".xml",
    }
    document_like = {".txt", ".md", ".markdown", ".csv", ".log"}
    if suffix in code_like or suffix not in document_like:
        return
    context_store.record_document_context(path=rel_path, content=content, task_id=task_id, activate=True)


def execute_local_action(action: str, action_input: str, *, task_id: str | None = None) -> str:
    normalized_action = action.strip().upper()

    try:
        if normalized_action == "READ_SKILL":
            skill_path = safe_child_path(SKILLS_DIR, action_input.strip(), expected_suffix=".md")
            return read_limited_text(skill_path)

        if normalized_action == "USE_TOOL":
            payload = json.loads(action_input)
            if not isinstance(payload, dict):
                return json_observation({"ok": False, "error": "Action Input 必须是 JSON object"})

            tool_name = str(payload.get("tool_name") or payload.get("tool") or "").strip().upper()
            args = payload.get("args") or {}
            if not isinstance(args, dict):
                return json_observation({"ok": False, "error": "args 必须是 JSON object"})

            return _execute_local_tool(tool_name, args, task_id=task_id)

        return json_observation({"ok": False, "error": f"未知 Action：{action}"})

    except json.JSONDecodeError as exc:
        return json_observation({"ok": False, "error": f"JSON 解析失败：{exc}"})
    except Exception as exc:
        return json_observation({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _execute_local_tool(tool_name: str, args: dict[str, Any], *, task_id: str | None = None) -> str:
    if tool_name == "LOCAL_ECHO":
        return json_observation({"ok": True, "echo": str(args.get("text", ""))})

    if tool_name == "COUNT_TEXT_CHARS":
        text = str(args.get("text", ""))
        return json_observation({"ok": True, "chars": len(text)})

    if tool_name == "LIST_SKILLS":
        skills = sorted(path.name for path in SKILLS_DIR.glob("*.md") if path.is_file())
        return json_observation({"ok": True, "skills": skills})

    if tool_name == "LIST_TODO_TASKS":
        query = str(args.get("query", "")).strip()
        if query:
            return json_observation({"ok": True, "tasks": todo_store.find_tasks(query, limit=int(args.get("limit", 20)))})
        return json_observation({"ok": True, "tasks": todo_store.list_tasks(limit=int(args.get("limit", 50)))})

    if tool_name == "ADD_TODO_TASK":
        return json_observation({"ok": True, "task": todo_store.add_task(args)})

    if tool_name == "UPDATE_TODO_TASK":
        task, error = _resolve_todo_task(args)
        if error:
            return json_observation({"ok": False, "error": error})
        fields = {key: args[key] for key in ("title", "description", "priority", "completed", "category", "due_date") if key in args}
        if not fields:
            return json_observation({"ok": False, "error": "没有可更新的日程字段"})
        return json_observation({"ok": True, "task": todo_store.update_task(task["id"], fields)})

    if tool_name == "COMPLETE_TODO_TASK":
        task, error = _resolve_todo_task(args, include_completed=False)
        if error:
            return json_observation({"ok": False, "error": error})
        return json_observation({"ok": True, "task": todo_store.update_task(task["id"], {"completed": True})})

    if tool_name == "DELETE_TODO_TASK":
        task, error = _resolve_todo_task(args)
        if error:
            return json_observation({"ok": False, "error": error})
        return json_observation({"ok": todo_store.delete_task(task["id"]), "task": task})

    if tool_name == "APPLY_TODO_INSTRUCTION":
        instruction = str(args.get("instruction") or args.get("text") or args.get("prompt") or "")
        return json_observation(todo_store.apply_instruction(instruction))

    if tool_name == "READ_LAST_OCR_RESULT":
        return json_observation(read_latest_ocr_result(args))

    if tool_name == "SAFE_READ_TEXT_FILE":
        rel_path = str(args.get("path", ""))
        file_path = safe_child_path(WORKSPACE_DIR, rel_path)
        content = read_limited_text(file_path)
        _maybe_record_document_context(rel_path, content, task_id=task_id)
        return json_observation(
            {
                "ok": True,
                "path": rel_path,
                "content": content,
            }
        )

    if tool_name == "SAFE_WRITE_TEXT_FILE":
        rel_path = str(args.get("path", ""))
        text = str(args.get("text", ""))
        overwrite = bool(args.get("overwrite", False))
        file_path = safe_child_path(WORKSPACE_DIR, rel_path)
        write_limited_text(file_path, text, overwrite=overwrite)
        return json_observation({"ok": True, "path": rel_path, "bytes": len(text.encode("utf-8"))})

    if tool_name == "FORMAT_MEETING_MINUTES":
        if task_id and not args.get("task_id"):
            args = {**args, "task_id": task_id}
        return json_observation(format_meeting_minutes(args))

    if tool_name in {"PARSE_DOCUMENT_WITH_OCR_PC", "OCR_PC_PARSE_DOCUMENT"}:
        if task_id and not args.get("task_id"):
            args = {**args, "task_id": task_id}
        return json_observation(parse_document_with_ocr_pc(args))

    return json_observation({"ok": False, "error": f"未知本地工具：{tool_name}"})


def _resolve_todo_task(args: dict[str, Any], *, include_completed: bool = True) -> tuple[dict[str, Any] | None, str]:
    if args.get("id") is not None:
        task = todo_store.get_task(args["id"])
        return (task, "") if task else (None, "日程不存在")

    query = str(args.get("query") or args.get("title") or "").strip()
    if not query:
        return None, "请提供日程 id 或 query/title"

    matches = todo_store.find_tasks(query, include_completed=include_completed, limit=10)
    exact = [task for task in matches if task["title"] == query]
    if exact:
        matches = exact
    if not matches:
        return None, f"没有找到匹配“{query}”的日程"
    if len(matches) > 1:
        titles = "；".join(f"{task['id']}:{task['title']}" for task in matches[:5])
        return None, f"找到多条匹配“{query}”的日程，请指定 id。候选：{titles}"
    return matches[0], ""
