from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import task_store
from .heavy_runtime import get_active_engine, is_llama_server_running
from .paths import WORKSPACE_DIR


EVENT_USER_MESSAGE = "USER_MESSAGE"
EVENT_PLAN_REQUESTED = "PLAN_REQUESTED"
EVENT_TOOL_REQUESTED = "TOOL_REQUESTED"
EVENT_OCR_REQUIRED = "OCR_REQUIRED"
EVENT_ASR_SEGMENT_READY = "ASR_SEGMENT_READY"
EVENT_REVIEW_REQUESTED = "REVIEW_REQUESTED"
EVENT_TASK_DONE = "TASK_DONE"
EVENT_ERROR = "ERROR"

MAX_PROMPT_CHARS = int(os.environ.get("AGENT_MAX_PROMPT_CHARS", "24000"))
CONVERSATION_CONTEXT_TURNS = int(os.environ.get("AGENT_CONVERSATION_CONTEXT_TURNS", "6"))
CONVERSATION_CONTEXT_CHARS = int(os.environ.get("AGENT_CONVERSATION_CONTEXT_CHARS", "8000"))
CONVERSATION_TURN_CHARS = int(os.environ.get("AGENT_CONVERSATION_TURN_CHARS", "1400"))
DEFAULT_EVENT_WAIT_SECONDS = 0.25

_agent_lock = threading.Lock()
_task_threads: dict[str, threading.Thread] = {}
_task_threads_lock = threading.Lock()
LLAMA_CPP_BACKEND = "llama_cpp"


@dataclass
class SharedState:
    task_id: str
    prompt: str
    backend: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    conversation_context: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    past_steps: list[tuple[Any, Any]] = field(default_factory=list)
    current_response: str = ""
    resource_state: str = "IDLE"
    checkpoint: dict[str, Any] = field(default_factory=dict)


def start_task(
    prompt: str,
    *,
    backend: str = LLAMA_CPP_BACKEND,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if backend and backend != LLAMA_CPP_BACKEND:
        raise ValueError("当前项目只支持 llama.cpp 后端")
    normalized_prompt = _compose_prompt(prompt, attachments or [])
    if not normalized_prompt.strip():
        raise ValueError("prompt 不能为空")
    task_id = uuid.uuid4().hex[:12]
    task = task_store.create_task(task_id, prompt=normalized_prompt, backend=LLAMA_CPP_BACKEND, attachments=attachments or [])
    thread = threading.Thread(
        target=_run_task_thread,
        args=(task_id,),
        name=f"agent-task-{task_id}",
        daemon=True,
    )
    with _task_threads_lock:
        _task_threads[task_id] = thread
    thread.start()
    return task


def wait_for_task(task_id: str, *, timeout_seconds: float = 180) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task = task_store.get_task(task_id)
        if task and task["status"] in task_store.TERMINAL_TASK_STATUSES:
            return task
        time.sleep(DEFAULT_EVENT_WAIT_SECONDS)
    return task_store.get_task(task_id)


def features() -> list[dict[str, Any]]:
    return [
        {
            "id": "read-file",
            "title": "文件读取",
            "description": "读取 workspace_files 内的文本文件并总结。",
            "needsFile": True,
            "prompt": "请读取文件 {path}，总结主要内容，并列出关键事实。",
        },
        {
            "id": "parse-file",
            "title": "文件解析",
            "description": "调用 OCR/PaddleOCR 解析 PDF 或图片文件。",
            "needsFile": True,
            "prompt": (
                "请使用 PARSE_DOCUMENT_WITH_OCR_PC 解析文件 {path}，返回 Markdown、"
                "content_list_v2、图片目录，并总结 OCR 解析结果。"
            ),
        },
        {
            "id": "summarize",
            "title": "内容摘要生成",
            "description": "对输入内容生成结构化摘要。",
            "needsFile": False,
            "prompt": "请对下面内容生成结构化摘要，包含主题、关键结论、待办事项：\n\n",
        },
        {
            "id": "data-insight",
            "title": "数据洞察分析",
            "description": "分析文本或表格中的趋势与异常。",
            "needsFile": False,
            "prompt": "请分析下面数据，找出异常趋势、可能原因和下一步建议：\n\n",
        },
        {
            "id": "code-review",
            "title": "代码 Review",
            "description": "检查代码风险、可维护性和测试缺口。",
            "needsFile": True,
            "prompt": "请读取代码文件 {path}，做一次代码 Review，按严重程度列出问题和修改建议。",
        },
        {
            "id": "list-skills",
            "title": "列出技能",
            "description": "查看当前本地 Skill.md 能力。",
            "needsFile": False,
            "prompt": "请列出当前可用技能，并说明每个技能适合处理什么任务。",
        },
        {
            "id": "meeting-summary",
            "title": "会议总结",
            "description": "总结当前会议转写，提取结论和待办。",
            "needsFile": False,
            "action": "meeting-summary",
            "prompt": "请总结当前会议记录，输出会议纪要、关键结论和待办事项。",
        },
        {
            "id": "meeting-minutes-export",
            "title": "会议纪要导出",
            "description": "把会议转写排版为 Markdown、Typst 和 PDF 文件。",
            "needsFile": True,
            "prompt": "请将会议转写文件 {path} 格式化排版成会议纪要，使用 Typst 模板并导出 PDF。",
        },
    ]


def compact_text_for_llm(text: str, *, max_chars: int = MAX_PROMPT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    return (
        text[:head_chars]
        + "\n\n[内容过长，已按内存预算截断，中间部分将在后续分块处理中继续处理]\n\n"
        + text[-tail_chars:]
    )


def chunk_text(text: str, *, max_chars: int = 6000) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in text.splitlines(keepends=True):
        if current and current_len + len(paragraph) > max_chars:
            chunks.append("".join(current).strip())
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def build_conversation_context(*, exclude_task_id: str = "") -> str:
    """Build a small recent chat window from completed persisted tasks."""
    if CONVERSATION_CONTEXT_TURNS <= 0 or CONVERSATION_CONTEXT_CHARS <= 0:
        return ""

    recent_tasks = task_store.list_tasks(limit=max(CONVERSATION_CONTEXT_TURNS * 3, 12))
    turns: list[str] = []
    budget = CONVERSATION_CONTEXT_CHARS

    for task in recent_tasks:
        if task.get("id") == exclude_task_id:
            continue
        if task.get("status") != "completed":
            continue
        result = str(task.get("result") or "").strip()
        if not result:
            continue

        prompt = _strip_attachment_block(str(task.get("prompt") or "").strip())
        turn = (
            f"User: {_clip_for_context(prompt, CONVERSATION_TURN_CHARS)}\n"
            f"Assistant: {_clip_for_context(result, CONVERSATION_TURN_CHARS)}"
        )
        if len(turn) > budget and turns:
            break
        if len(turn) > budget:
            turn = turn[-budget:]
        turns.append(turn)
        budget -= len(turn)
        if len(turns) >= CONVERSATION_CONTEXT_TURNS or budget <= 0:
            break

    if not turns:
        return ""
    return "\n\n".join(reversed(turns))


def _strip_attachment_block(text: str) -> str:
    return re.sub(r"<attachments>.*?</attachments>", "[attachments omitted]", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _clip_for_context(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - 40)
    return text[: keep // 2] + "\n...[已截断]...\n" + text[-(keep - keep // 2) :]


def _run_task_thread(task_id: str) -> None:
    try:
        with _agent_lock:
            _run_task(task_id)
    finally:
        with _task_threads_lock:
            _task_threads.pop(task_id, None)


def _run_task(task_id: str) -> None:
    task = task_store.get_task(task_id)
    if not task:
        return

    state = SharedState(
        task_id=task_id,
        prompt=task["prompt"],
        backend=task["backend"],
        attachments=task.get("attachments", []),
        resource_state=get_active_engine(),
    )

    try:
        task_store.update_task(task_id, status="running")
        state.conversation_context = build_conversation_context(exclude_task_id=task_id)
        _event(state, EVENT_USER_MESSAGE, "接收任务", state.prompt[:1200], {"attachments": state.attachments})
        if state.conversation_context:
            _event(
                state,
                "CONTEXT_LOADED",
                "加载聊天上下文",
                state.conversation_context[:1200],
                {"chars": len(state.conversation_context)},
            )
        _event(state, EVENT_PLAN_REQUESTED, "Planner 开始规划", "读取 Skill 索引，生成可执行步骤。")
        _event(
            state,
            "RESOURCE_SNAPSHOT",
            "资源状态快照",
            f"heavy_engine={get_active_engine()}, llama_server={is_llama_server_running()}",
        )

        result_state = _run_graph(state)
        state.plan = list(result_state.get("plan", []))
        state.past_steps = list(result_state.get("past_steps", []))
        state.current_response = str(result_state.get("current_response", "")).strip()

        _emit_step_events(state)
        _event(state, EVENT_REVIEW_REQUESTED, "Reviewer 进行结果检查", "检查输出是否为空、工具是否失败、是否需要补充执行。")
        review = _review_result(state)
        _event(state, "REVIEW_DONE", "Reviewer 完成检查", review["message"], review)

        _event(state, EVENT_TASK_DONE, "任务完成", state.current_response, {"review": review})
        task_store.update_task(task_id, status="completed", result=state.current_response)
    except Exception as exc:  # noqa: BLE001 - task boundary must persist failures
        message = f"{type(exc).__name__}: {exc}"
        task_store.update_task(task_id, status="failed", error=message)
        _event(state, EVENT_ERROR, "任务失败", message)


def _run_graph(state: SharedState) -> dict[str, Any]:
    from .graph import run_agent, user_visible_response

    graph_state = run_agent(
        compact_text_for_llm(state.prompt),
        task_id=state.task_id,
        conversation_context=state.conversation_context,
    )
    graph_state["current_response"] = user_visible_response(graph_state)
    return dict(graph_state)


def _emit_step_events(state: SharedState) -> None:
    for index, item in enumerate(state.past_steps, start=1):
        action_info, observation = item
        action = action_info[0] if isinstance(action_info, tuple) and action_info else str(action_info)
        action_input = action_info[1] if isinstance(action_info, tuple) and len(action_info) > 1 else ""
        event_type = EVENT_OCR_REQUIRED if "OCR" in str(action_input).upper() else EVENT_TOOL_REQUESTED
        _event(
            state,
            event_type,
            f"执行步骤 {index}: {action}",
            str(observation)[:2000],
            {"index": index, "action": action, "action_input": str(action_input)[:2000]},
        )


def _review_result(state: SharedState) -> dict[str, Any]:
    failed_observations = []
    for _, observation in state.past_steps:
        try:
            payload = json.loads(str(observation))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("ok") is False:
            failed_observations.append(payload.get("error", "未知工具错误"))

    if failed_observations:
        return {
            "ok": False,
            "message": "发现工具执行失败，结果需要人工复核。",
            "errors": failed_observations,
        }
    if not state.current_response.strip():
        return {"ok": False, "message": "最终响应为空，任务需要重试。"}
    return {"ok": True, "message": "结果非空，工具执行未发现失败。"}


def _event(
    state: SharedState,
    event_type: str,
    title: str,
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    task_store.add_event(
        state.task_id,
        event_type,
        title,
        message,
        {
            "resource_state": get_active_engine(),
            "checkpoint": state.checkpoint,
            **(payload or {}),
        },
    )


def _compose_prompt(prompt: str, attachments: list[dict[str, Any]]) -> str:
    text = compact_text_for_llm(prompt.strip())
    if not attachments:
        return text
    lines = [text, "", "<attachments>"]
    for item in attachments:
        path = str(item.get("path", "")).strip()
        name = str(item.get("name", Path(path).name)).strip()
        if path:
            _assert_workspace_relative(path)
            lines.append(f"- {name}: {path}")
    lines.append("</attachments>")
    return "\n".join(lines).strip()


def _assert_workspace_relative(path: str) -> None:
    candidate = (WORKSPACE_DIR / path).resolve()
    candidate.relative_to(WORKSPACE_DIR.resolve())
