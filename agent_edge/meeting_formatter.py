from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT, WORKSPACE_DIR, safe_child_path


TEMPLATE_DIR = PROJECT_ROOT / "templates" / "meeting_minutes"
DEFAULT_TEMPLATE = "standard"
MAX_TRANSCRIPT_CHARS = 24000


def format_meeting_minutes(args: dict[str, Any]) -> dict[str, Any]:
    transcript, source_path = _load_transcript(args)
    cleaned = _clean_transcript(transcript)
    if not cleaned.strip():
        raise ValueError("会议转写内容为空，无法生成会议纪要。")

    use_llm = bool(args.get("use_llm", True))
    if use_llm:
        minutes = _generate_minutes_with_llm(
            transcript=cleaned,
            title=str(args.get("title") or "").strip(),
            source_path=source_path,
        )
    else:
        minutes = _fallback_minutes(cleaned, title=str(args.get("title") or "").strip(), source_path=source_path)

    minutes = _normalize_minutes(minutes, transcript=cleaned, source_path=source_path)
    output_dir = _output_dir(minutes=minutes, source_path=source_path, task_id=str(args.get("task_id") or ""))
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "minutes.json"
    markdown_path = output_dir / "minutes.md"
    typ_path = output_dir / "minutes.typ"
    transcript_path = output_dir / "transcript.txt"
    pdf_path = output_dir / "minutes.pdf"

    json_path.write_text(json.dumps(minutes, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    markdown_path.write_text(_render_markdown(minutes), encoding="utf-8", newline="\n")
    typ_path.write_text(_render_typst(minutes, template=str(args.get("template") or DEFAULT_TEMPLATE)), encoding="utf-8", newline="\n")
    transcript_path.write_text(cleaned, encoding="utf-8", newline="\n")

    typst_result = _compile_typst(typ_path=typ_path, pdf_path=pdf_path)

    return {
        "ok": True,
        "title": minutes["title"],
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "typ_path": str(typ_path),
        "pdf_path": str(pdf_path) if typst_result["ok"] else None,
        "transcript_path": str(transcript_path),
        "typst": typst_result,
        "summary": minutes.get("summary", ""),
        "todo_count": len(minutes.get("todos", [])),
        "risk_count": len(minutes.get("risks", [])),
    }


def _load_transcript(args: dict[str, Any]) -> tuple[str, Path | None]:
    direct_text = str(args.get("transcript") or args.get("text") or "").strip()
    if direct_text:
        return direct_text, None

    rel_path = str(args.get("path") or args.get("transcript_path") or "").strip()
    if rel_path:
        path = safe_child_path(WORKSPACE_DIR, rel_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8", errors="replace")[-MAX_TRANSCRIPT_CHARS:], path

    try:
        from .meeting_asr import meeting_status

        status = meeting_status()
        transcript = str(status.get("transcript") or "").strip()
        transcript_path = status.get("transcript_path")
        source_path = Path(str(transcript_path)) if transcript_path else None
        if transcript:
            return transcript[-MAX_TRANSCRIPT_CHARS:], source_path
    except Exception:
        pass

    raise ValueError("请提供会议转写文件 path，或先通过会议记录生成 transcript。")


def _generate_minutes_with_llm(*, transcript: str, title: str, source_path: Path | None) -> dict[str, Any]:
    from .llm import llm_call

    source_name = source_path.name if source_path else "当前会议转写"
    prompt = f"""
你是离线端会议纪要整理器。请严格根据会议转写生成结构化 JSON，不要编造未出现的信息。

输出必须是一个 JSON object，不要 Markdown，不要代码块。
字段：
- title: 字符串
- date: 字符串，优先使用转写里的日期，没有则留空
- participants: 字符串数组，无法确认则 []
- summary: 80-200 字中文摘要
- topics: 数组，每项包含 name、discussion、decisions
- decisions: 字符串数组
- todos: 数组，每项包含 task、owner、deadline、status
- risks: 字符串数组

规则：
- 如果转写内容太少或噪声很大，要在 summary 或 risks 里说明。
- owner/deadline 不确定时写“待定”。
- 不要输出 Action/Observation。

用户指定标题：{title or "未指定"}
来源文件：{source_name}

会议转写：
{transcript[:MAX_TRANSCRIPT_CHARS]}
""".strip()
    raw = llm_call(prompt)
    return _extract_json_object(raw)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"LLM 未输出可解析的会议纪要 JSON：{raw[:300]}")


def _normalize_minutes(minutes: dict[str, Any], *, transcript: str, source_path: Path | None) -> dict[str, Any]:
    fallback = _fallback_minutes(transcript, title=str(minutes.get("title") or ""), source_path=source_path)
    title = str(minutes.get("title") or fallback["title"]).strip() or "会议纪要"
    meeting_date = str(minutes.get("date") or fallback["date"]).strip()

    return {
        "schema_version": "meeting_minutes_v1",
        "title": title,
        "date": meeting_date,
        "source": str(source_path) if source_path else "current_meeting_transcript",
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "participants": _string_list(minutes.get("participants")),
        "summary": str(minutes.get("summary") or fallback["summary"]).strip(),
        "topics": _topics(minutes.get("topics")),
        "decisions": _string_list(minutes.get("decisions")),
        "todos": _todos(minutes.get("todos")),
        "risks": _string_list(minutes.get("risks")),
        "transcript_excerpt": transcript[:4000],
    }


def _fallback_minutes(transcript: str, *, title: str, source_path: Path | None) -> dict[str, Any]:
    segments = _timestamped_segments(transcript)
    content_lines = [text for _, text in segments] or [line.strip() for line in transcript.splitlines() if line.strip()]
    excerpt = " ".join(content_lines[:6]).strip()
    meeting_date = _infer_meeting_date(transcript, source_path)
    return {
        "title": title or "会议纪要",
        "date": meeting_date,
        "participants": [],
        "summary": excerpt[:220] if excerpt else "会议转写内容较少，暂无法生成充分摘要。",
        "topics": [{"name": "会议讨论", "discussion": content_lines[:8], "decisions": []}],
        "decisions": [],
        "todos": [],
        "risks": ["会议纪要由转写文本自动生成，可能存在 ASR 识别噪声。"],
    }


def _clean_transcript(transcript: str) -> str:
    lines: list[str] = []
    for raw in transcript.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        if set(line) <= {"="}:
            continue
        if line in {"录音记录", "錄音記錄"}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _timestamped_segments(transcript: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    for line in transcript.splitlines():
        match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+?)\s*$", line.strip())
        if match:
            segments.append((match.group(1), match.group(2)))
    return segments


def _infer_meeting_date(transcript: str, source_path: Path | None) -> str:
    match = re.search(r"开始时间[:：]\s*(\d{4}-\d{2}-\d{2})", transcript)
    if match:
        return match.group(1)
    if source_path:
        match = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", source_path.name)
        if match:
            return "-".join(match.groups())
    return dt.date.today().isoformat()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("name") or item.get("task") or item.get("content")
            else:
                text = item
            normalized = str(text or "").strip()
            if normalized:
                result.append(normalized)
        return result
    return [str(value).strip()] if str(value).strip() else []


def _topics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    topics: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or f"议题 {index}").strip()
            discussion = _string_list(item.get("discussion") or item.get("points") or item.get("summary"))
            decisions = _string_list(item.get("decisions"))
        else:
            name = str(item).strip() or f"议题 {index}"
            discussion = []
            decisions = []
        topics.append({"name": name, "discussion": discussion, "decisions": decisions})
    return topics


def _todos(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    todos: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            task = str(item.get("task") or item.get("title") or item.get("content") or "").strip()
            owner = str(item.get("owner") or "待定").strip() or "待定"
            deadline = str(item.get("deadline") or item.get("due") or "待定").strip() or "待定"
            status = str(item.get("status") or "待处理").strip() or "待处理"
        else:
            task = str(item).strip()
            owner = "待定"
            deadline = "待定"
            status = "待处理"
        if task:
            todos.append({"task": task, "owner": owner, "deadline": deadline, "status": status})
    return todos


def _output_dir(*, minutes: dict[str, Any], source_path: Path | None, task_id: str) -> Path:
    source_name = source_path.stem if source_path else "current_meeting"
    digest_source = (str(source_path) if source_path else minutes.get("summary", "")) + str(minutes.get("generated_at", ""))
    digest = hashlib.sha1(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:8]
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = task_id[:8] if task_id else digest
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_name).strip("_") or "meeting"
    return WORKSPACE_DIR / "meeting_outputs" / f"{stamp}_{safe_name}_{suffix}"


def _render_markdown(minutes: dict[str, Any]) -> str:
    lines = [
        f"# {minutes['title']}",
        "",
        "## 基本信息",
        f"- 日期：{minutes.get('date') or '待定'}",
        f"- 来源：{minutes.get('source') or '未知'}",
        f"- 生成时间：{minutes.get('generated_at')}",
        f"- 参会人：{', '.join(minutes.get('participants') or []) or '待定'}",
        "",
        "## 摘要",
        str(minutes.get("summary") or "暂无摘要。"),
        "",
        "## 议题与讨论",
    ]
    for topic in minutes.get("topics") or []:
        lines.extend([f"### {topic.get('name') or '未命名议题'}"])
        lines.extend(f"- {item}" for item in topic.get("discussion") or ["暂无讨论要点。"])
        decisions = topic.get("decisions") or []
        if decisions:
            lines.append("")
            lines.append("结论：")
            lines.extend(f"- {item}" for item in decisions)
        lines.append("")

    lines.extend(["## 关键结论", *_markdown_list(minutes.get("decisions"), empty="暂无明确结论。"), ""])
    lines.extend(["## 待办事项"])
    todos = minutes.get("todos") or []
    if todos:
        lines.append("| 事项 | 负责人 | 截止时间 | 状态 |")
        lines.append("| --- | --- | --- | --- |")
        for item in todos:
            lines.append(f"| {item['task']} | {item['owner']} | {item['deadline']} | {item['status']} |")
    else:
        lines.append("暂无明确待办事项。")
    lines.extend(["", "## 风险与待确认", *_markdown_list(minutes.get("risks"), empty="暂无明确风险。"), ""])
    return "\n".join(lines).strip() + "\n"


def _markdown_list(items: Any, *, empty: str) -> list[str]:
    values = _string_list(items)
    return [f"- {item}" for item in values] if values else [empty]


def _render_typst(minutes: dict[str, Any], *, template: str) -> str:
    template_path = TEMPLATE_DIR / f"{template}.typ"
    if not template_path.exists():
        template_path = TEMPLATE_DIR / f"{DEFAULT_TEMPLATE}.typ"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "title": _typst_text(minutes["title"]),
        "metadata": _typst_metadata(minutes),
        "summary": _typst_paragraph(minutes.get("summary") or "暂无摘要。"),
        "topics": _typst_topics(minutes.get("topics") or []),
        "decisions": _typst_bullets(minutes.get("decisions"), empty="暂无明确结论。"),
        "todos": _typst_todos(minutes.get("todos") or []),
        "risks": _typst_bullets(minutes.get("risks"), empty="暂无明确风险。"),
        "transcript_excerpt": _typst_paragraph(str(minutes.get("transcript_excerpt") or "暂无转写节选。")),
    }
    rendered = template_text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _typst_metadata(minutes: dict[str, Any]) -> str:
    participants = "、".join(minutes.get("participants") or []) or "待定"
    rows = [
        f"- 日期：{_typst_text(minutes.get('date') or '待定')}",
        f"- 来源：{_typst_text(minutes.get('source') or '未知')}",
        f"- 生成时间：{_typst_text(minutes.get('generated_at') or '')}",
        f"- 参会人：{_typst_text(participants)}",
    ]
    return "\n".join(rows)


def _typst_topics(topics: list[dict[str, Any]]) -> str:
    if not topics:
        return "暂无明确议题。"
    parts: list[str] = []
    for topic in topics:
        parts.append(f"=== {_typst_text(topic.get('name') or '未命名议题')}")
        parts.append(_typst_bullets(topic.get("discussion"), empty="暂无讨论要点。"))
        decisions = topic.get("decisions") or []
        if decisions:
            parts.append("*结论：*")
            parts.append(_typst_bullets(decisions, empty=""))
    return "\n\n".join(part for part in parts if part)


def _typst_todos(todos: list[dict[str, str]]) -> str:
    if not todos:
        return "暂无明确待办事项。"
    lines = []
    for item in todos:
        lines.append(
            f"- {_typst_text(item['task'])}（负责人：{_typst_text(item['owner'])}；"
            f"截止：{_typst_text(item['deadline'])}；状态：{_typst_text(item['status'])}）"
        )
    return "\n".join(lines)


def _typst_bullets(items: Any, *, empty: str) -> str:
    values = _string_list(items)
    if not values:
        return empty
    return "\n".join(f"- {_typst_text(item)}" for item in values)


def _typst_paragraph(text: str) -> str:
    return _typst_text(text).replace("\n", "\n\n")


def _typst_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\\": "\\\\",
        "#": "\\#",
        "$": "\\$",
        "%": "\\%",
        "&": "\\&",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
    }
    return "".join(replacements.get(char, char) for char in text)


def _compile_typst(*, typ_path: Path, pdf_path: Path) -> dict[str, Any]:
    typst_bin = _resolve_typst_bin()
    if not typst_bin:
        return {
            "ok": False,
            "compiled": False,
            "error": "typst 命令未安装，已生成 .typ 和 .md 文件。请设置 TYPST_BIN，或将 typst 放到 .runtime/bin/typst。",
        }
    try:
        completed = subprocess.run(
            [typst_bin, "compile", str(typ_path), str(pdf_path)],
            cwd=str(typ_path.parent),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - return tool-friendly diagnostics
        return {"ok": False, "compiled": False, "error": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        return {
            "ok": False,
            "compiled": False,
            "error": (completed.stderr or completed.stdout or "typst compile failed")[:1000],
        }
    return {"ok": True, "compiled": True, "pdf_path": str(pdf_path)}


def _resolve_typst_bin() -> str | None:
    configured = os.environ.get("TYPST_BIN", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.exists() and path.is_file():
            return str(path)

    bundled_candidates = [
        PROJECT_ROOT / ".runtime" / "bin" / "typst",
        PROJECT_ROOT / ".runtime" / "bin" / "typst.exe",
    ]
    for candidate in bundled_candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return shutil.which("typst")
