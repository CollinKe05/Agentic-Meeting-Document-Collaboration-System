from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import context_store
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
