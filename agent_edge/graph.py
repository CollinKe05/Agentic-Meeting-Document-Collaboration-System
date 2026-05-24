from __future__ import annotations

import copy
import json
import re
import warnings
from pathlib import Path
from typing import Any, Dict, Literal

from langchain_core._api.deprecation import (
    LangChainDeprecationWarning,
    LangChainPendingDeprecationWarning,
)

warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

from langgraph.graph import END, START, StateGraph

from .llm import fallback_plan, llm_call
from .local_actions import execute_local_action
from .parsing import parse_json_list, parse_react_output, strip_route_marker
from .paths import ensure_demo_assets
from .state import AgentState


ROUTE_PREFIX = "__route__:"
MAX_ATTEMPTS_PER_STEP = 3
TEXT_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".csv",
    ".toml",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".sh",
    ".ps1",
    ".cmd",
    ".bat",
    ".xml",
    ".ini",
    ".cfg",
    ".log",
}
MINERU_FILE_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
TOOL_INTENT_KEYWORDS = {
    "文件",
    "读取",
    "读一下",
    "打开",
    "上传",
    "解析",
    "mineru",
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "图片",
    "ocr",
    "技能",
    "skill",
    "工具",
    "tool",
    "统计",
    "写入",
    "保存",
    "workspace",
    "uploads",
    "content_list",
}


def planner_node(state: AgentState) -> Dict[str, Any]:
    """规划节点：读取本地技能索引，让本地模型输出 JSON 计划。"""
    ensure_demo_assets()
    skills_index = execute_local_action("READ_SKILL", "skills_index.md")

    prompt = f"""
[PLANNER]
你是一个完全离线运行的边缘设备 AI Agent Planner。
你必须基于用户输入和本地技能索引，生成严格 JSON list。
不要输出 Markdown，不要解释，不要调用云端工具。

<user_input>
{state["user_input"]}
</user_input>

<skills_index>
{skills_index}
</skills_index>

输出 schema:
[
  {{
    "id": 1,
    "kind": "learn_skill 或 use_tool",
    "objective": "步骤目标",
    "skill_file": "当 kind=learn_skill 时填写，例如 read_file_skill.md",
    "tool_name": "当 kind=use_tool 时填写，例如 SAFE_READ_TEXT_FILE",
    "tool_input": {{"path": "demo_input.txt"}},
    "status": "todo",
    "attempts": 0
  }}
]

规划要求：
- 使用 Plan-and-Solve 拆解任务。
- 内部可以比较多条路径，但最终只能输出一个线性 JSON list。
- 至少包含一个 learn_skill 步骤和一个 use_tool 步骤。
- 如果用户没有指定文件，默认读取 demo_input.txt。
- 如果用户要求解析 PDF、图片、DOCX、PPTX 或 XLSX，优先学习 local_tool_skill.md，并调用 PARSE_DOCUMENT_WITH_MINERU。
"""

    raw = llm_call(prompt)
    try:
        plan = parse_json_list(raw)
        note = f"Planner 已通过本地模型生成 {len(plan)} 个步骤。"
    except Exception as exc:
        plan = fallback_plan(state["user_input"])
        note = f"Planner 输出解析失败，已使用本地 fallback plan：{type(exc).__name__}: {exc}"

    normalized = _normalize_plan(plan, state["user_input"])

    return {
        "plan": normalized,
        "past_steps": state.get("past_steps", []),
        "current_response": f"{ROUTE_PREFIX}next_task\n{note}",
    }


def executor_node(state: AgentState) -> Dict[str, Any]:
    """执行节点：按 ReAct 风格执行队首任务，并把 Observation 写回状态。"""
    plan = copy.deepcopy(state.get("plan", []))
    past_steps = list(state.get("past_steps", []))

    if not plan:
        return {
            "plan": [],
            "past_steps": past_steps,
            "current_response": f"{ROUTE_PREFIX}end\n全部任务已完成。",
        }

    current_task = plan.pop(0)
    attempts = int(current_task.get("attempts", 0))

    if current_task.get("last_observation"):
        return _finish_observed_task(plan, past_steps, current_task)

    if attempts >= MAX_ATTEMPTS_PER_STEP:
        current_task["status"] = "failed"
        current_task["result"] = "超过最大尝试次数，已跳过。"
        past_steps.append((("FINISH", f"step={current_task.get('id')}"), current_task["result"]))
        route = "next_task" if plan else "end"
        response = _build_summary(past_steps, state["user_input"]) if route == "end" else current_task["result"]
        return {"plan": plan, "past_steps": past_steps, "current_response": f"{ROUTE_PREFIX}{route}\n{response}"}

    prompt = _build_executor_prompt(current_task, past_steps[-8:])

    raw = ""
    try:
        raw = llm_call(prompt)
        thought, action, action_input = parse_react_output(raw)
    except Exception as exc:
        thought = f"模型 ReAct 输出解析失败，使用任务 schema 兜底：{type(exc).__name__}: {exc}"
        action, action_input = _expected_action_for_task(current_task)
        current_task["last_model_output"] = raw[:800]

    action, action_input = _coerce_action_for_task(current_task, action, action_input)

    if action == "FINISH":
        current_task["status"] = "done"
        current_task["result"] = action_input
        past_steps.append((("FINISH", f"step={current_task.get('id')}"), action_input))

        route = "next_task" if plan else "end"
        response = (
            _build_summary(past_steps, state["user_input"])
            if route == "end"
            else f"步骤 {current_task.get('id')} 完成：{action_input}"
        )
        return {
            "plan": plan,
            "past_steps": past_steps,
            "current_response": f"{ROUTE_PREFIX}{route}\n{response}",
        }

    observation = execute_local_action(action, action_input)
    return _requeue_with_observation(plan, past_steps, current_task, action, action_input, observation, thought)


def route_after_executor(state: AgentState) -> Literal["react_loop", "next_task", "end"]:
    response = state.get("current_response", "")
    first_line = response.splitlines()[0] if response else ""

    if first_line.startswith(ROUTE_PREFIX):
        route = first_line.replace(ROUTE_PREFIX, "", 1).strip()
        if route in {"react_loop", "next_task", "end"}:
            return route  # type: ignore[return-value]

    return "next_task" if state.get("plan") else "end"


def build_agent_graph():
    builder = StateGraph(AgentState)

    builder.add_node("planner_node", planner_node)
    builder.add_node("executor_node", executor_node)

    builder.add_edge(START, "planner_node")
    builder.add_edge("planner_node", "executor_node")
    builder.add_conditional_edges(
        "executor_node",
        route_after_executor,
        {
            "react_loop": "executor_node",
            "next_task": "executor_node",
            "end": END,
        },
    )

    return builder.compile()


def run_agent(user_input: str) -> AgentState:
    if _should_direct_chat(user_input):
        return {
            "user_input": user_input,
            "plan": [],
            "past_steps": [],
            "current_response": llm_call(_build_direct_chat_prompt(user_input)),
        }

    app = build_agent_graph()
    initial_state: AgentState = {
        "user_input": user_input,
        "plan": [],
        "past_steps": [],
        "current_response": "",
    }
    return app.invoke(initial_state)


def user_visible_response(state: AgentState) -> str:
    return strip_route_marker(state.get("current_response", ""), ROUTE_PREFIX)


def _should_direct_chat(user_input: str) -> bool:
    text = user_input.strip()
    if not text:
        return False

    lowered = text.lower()
    if "<attachments>" in lowered:
        return False
    if _extract_workspace_file_path({}, text):
        return False
    return not any(keyword in lowered for keyword in TOOL_INTENT_KEYWORDS)


def _build_direct_chat_prompt(user_input: str) -> str:
    return f"""
你是一个运行在本地离线环境中的边缘端 Agent。
当前用户请求不需要读取文件、调用工具或解析文档。
请直接用中文自然回复用户，保持简洁、友好、可执行。
不要编造已经读取文件、已经调用工具、已经完成解析这类事实。

用户输入：
{user_input}
""".strip()


def _build_executor_prompt(current_task: dict[str, Any], recent_history: list[tuple]) -> str:
    return f"""
[EXECUTOR]
你是一个完全离线运行的边缘设备 AI Agent Executor。
请严格输出 ReAct 三段式，不要输出额外 Markdown。

Thought: ...
Action: READ_SKILL | USE_TOOL | FINISH
Action Input: ...

规则：
- 如果 current_task.kind 是 learn_skill，并且还没有 last_observation，使用 READ_SKILL。
- 如果 current_task.kind 是 use_tool，并且还没有 last_observation，使用 USE_TOOL。
- 如果已有 last_observation，基于 Observation 反思后 FINISH，避免重复调用。
- 如果 last_observation 表示错误，可以再尝试一次修正动作，但不要超过 attempts 限制。
- past_steps 是 Reflexion 记忆，用来避免重复同一个错误。

<current_task_json>
{json.dumps(current_task, ensure_ascii=False)}
</current_task_json>

<past_steps_json>
{json.dumps(recent_history, ensure_ascii=False, default=str)}
</past_steps_json>
"""


def _normalize_plan(plan: list[dict[str, Any]], user_input: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(plan, start=1):
        task = dict(item)
        task.setdefault("id", idx)
        task.setdefault("status", "todo")
        task.setdefault("attempts", 0)
        task.setdefault("objective", f"执行步骤 {idx}")

        kind = str(task.get("kind", "")).strip().lower()
        if kind not in {"learn_skill", "use_tool"}:
            if task.get("skill_file"):
                kind = "learn_skill"
            elif task.get("tool_name"):
                kind = "use_tool"
            else:
                kind = "use_tool"
                task["tool_name"] = "COUNT_TEXT_CHARS"
                task["tool_input"] = {"text": user_input}
        task["kind"] = kind

        if kind == "learn_skill":
            task.setdefault("skill_file", "skills_index.md")
        if kind == "use_tool":
            task.setdefault("tool_name", "COUNT_TEXT_CHARS")
            task.setdefault("tool_input", {"text": user_input})
            _repair_file_tool_route(task, user_input)

        normalized.append(task)

    if (
        len(normalized) < 2
        or not any(task.get("kind") == "learn_skill" for task in normalized)
        or not any(task.get("kind") == "use_tool" for task in normalized)
    ):
        return fallback_plan(user_input)

    return normalized


def _expected_action_for_task(current_task: dict[str, Any]) -> tuple[str, str]:
    last_observation = str(current_task.get("last_observation", ""))
    if last_observation:
        return "FINISH", f"当前步骤完成。Observation 摘要：{last_observation[:300]}"

    if current_task.get("kind") == "learn_skill":
        return "READ_SKILL", str(current_task.get("skill_file", "skills_index.md"))

    if current_task.get("kind") == "use_tool":
        payload = {
            "tool_name": current_task.get("tool_name", "COUNT_TEXT_CHARS"),
            "args": current_task.get("tool_input", {}),
        }
        return "USE_TOOL", json.dumps(payload, ensure_ascii=False)

    return "FINISH", "未知任务类型，已跳过。"


def _coerce_action_for_task(
    current_task: dict[str, Any], action: str, action_input: str
) -> tuple[str, str]:
    expected_action, expected_input = _expected_action_for_task(current_task)

    if current_task.get("last_observation"):
        return expected_action, expected_input

    if current_task.get("kind") in {"learn_skill", "use_tool"}:
        return expected_action, expected_input

    if action == "FINISH":
        return action, action_input or expected_input

    return action, action_input


def _repair_file_tool_route(task: dict[str, Any], user_input: str) -> None:
    tool_name = str(task.get("tool_name", "")).strip().upper()
    tool_input = task.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    path = _resolve_attachment_path(_extract_workspace_file_path(tool_input, user_input), user_input)
    if not path:
        return

    suffix = Path(path).suffix.lower()
    if suffix in TEXT_FILE_EXTENSIONS:
        task["tool_name"] = "SAFE_READ_TEXT_FILE"
        task["tool_input"] = {"path": path}
        return

    if suffix in MINERU_FILE_EXTENSIONS and tool_name in {"SAFE_READ_TEXT_FILE", "COUNT_TEXT_CHARS"}:
        task["tool_name"] = "PARSE_DOCUMENT_WITH_MINERU"
        task["tool_input"] = {"path": path}


def _extract_workspace_file_path(tool_input: dict[str, Any], user_input: str) -> str:
    for key in ("path", "file_path", "filename", "file"):
        value = tool_input.get(key)
        if isinstance(value, str) and Path(value).suffix:
            return value.strip()

    attachment_refs = _attachment_file_refs(user_input)
    if attachment_refs:
        return attachment_refs[0][1]

    extensions = sorted(TEXT_FILE_EXTENSIONS | MINERU_FILE_EXTENSIONS, key=len, reverse=True)
    pattern = r"([A-Za-z0-9_.\-/]+(?:%s))" % "|".join(re.escape(ext) for ext in extensions)
    match = re.search(pattern, user_input, flags=re.IGNORECASE)
    return match.group(1).strip("，。；;:,<>\"'") if match else ""


def _resolve_attachment_path(path: str, user_input: str) -> str:
    if not path:
        return ""
    normalized = path.strip()
    if normalized.startswith("uploads/"):
        return normalized

    path_name = Path(normalized).name
    for display_name, stored_path in _attachment_file_refs(user_input):
        stored_name = Path(stored_path).name
        if normalized in {display_name, stored_path, stored_name}:
            return stored_path
        if path_name in {display_name, stored_name}:
            return stored_path
        if stored_name.endswith(f"-{path_name}"):
            return stored_path
    return normalized


def _attachment_file_refs(user_input: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    match = re.search(r"<attachments>(.*?)</attachments>", user_input, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return refs

    extensions = sorted(TEXT_FILE_EXTENSIONS | MINERU_FILE_EXTENSIONS, key=len, reverse=True)
    ext_pattern = "|".join(re.escape(ext) for ext in extensions)
    line_pattern = re.compile(
        r"-\s*(?P<name>[^:\n]+?)\s*:\s*(?P<path>[A-Za-z0-9_.\-/]+(?:%s))" % ext_pattern,
        flags=re.IGNORECASE,
    )
    for line_match in line_pattern.finditer(match.group(1)):
        refs.append((line_match.group("name").strip(), line_match.group("path").strip()))
    return refs


def _finish_observed_task(
    plan: list[dict[str, Any]], past_steps: list[tuple], current_task: dict[str, Any]
) -> Dict[str, Any]:
    last_observation = str(current_task.get("last_observation", ""))
    result = f"当前步骤完成。Observation 摘要：{last_observation[:300]}"
    current_task["status"] = "done"
    current_task["result"] = result
    past_steps.append((("FINISH", f"step={current_task.get('id')}"), result))

    route = "next_task" if plan else "end"
    response = _build_summary(past_steps, "") if route == "end" else f"步骤 {current_task.get('id')} 完成：{result}"
    return {
        "plan": plan,
        "past_steps": past_steps,
        "current_response": f"{ROUTE_PREFIX}{route}\n{response}",
    }


def _requeue_with_observation(
    plan: list[dict[str, Any]],
    past_steps: list[tuple],
    current_task: dict[str, Any],
    action: str,
    action_input: str,
    observation: str,
    thought: str = "",
) -> Dict[str, Any]:
    current_task["status"] = "in_progress"
    current_task["attempts"] = int(current_task.get("attempts", 0)) + 1
    current_task["last_thought"] = thought
    current_task["last_action"] = action
    current_task["last_action_input"] = action_input
    current_task["last_observation"] = observation
    past_steps.append(((action, action_input), observation))
    plan.insert(0, current_task)

    return {
        "plan": plan,
        "past_steps": past_steps,
        "current_response": (
            f"{ROUTE_PREFIX}react_loop\n"
            f"步骤 {current_task.get('id')} 已执行 {action}，获得 Observation，进入下一轮反思。\n"
            f"Observation: {observation[:600]}"
        ),
    }


def _build_summary(past_steps: list[tuple], user_input: str = "") -> str:
    lines = ["全部任务完成。"]

    final_answer = _extract_final_answer(past_steps, user_input)
    if final_answer:
        lines.extend(["", "任务执行结果：", *final_answer])

    lines.extend(["", "执行历史摘要："])
    for idx, item in enumerate(past_steps, start=1):
        action_info, observation = item
        action_name = action_info[0] if isinstance(action_info, tuple) and action_info else str(action_info)
        lines.append(f"{idx}. Action={action_name} | Observation={str(observation)[:240]}")
    return "\n".join(lines)


def _extract_final_answer(past_steps: list[tuple], user_input: str = "") -> list[str]:
    answers: list[str] = []

    for action_info, observation in past_steps:
        action_name = action_info[0] if isinstance(action_info, tuple) and action_info else str(action_info)
        action_input = action_info[1] if isinstance(action_info, tuple) and len(action_info) > 1 else ""
        payload = _json_payload(observation)

        if action_name != "USE_TOOL" or not payload or payload.get("ok") is not True:
            continue

        tool_call = _json_payload(action_input)
        tool_name = str((tool_call or {}).get("tool_name") or (tool_call or {}).get("tool") or "").upper()

        if tool_name == "SAFE_READ_TEXT_FILE" and "content" in payload:
            path = payload.get("path", "文件")
            content = str(payload.get("content", "")).rstrip("\n")
            if _wants_content_summary(user_input):
                answers.append(_summarize_read_content(path=str(path), content=content, user_input=user_input))
            else:
                answers.append(f"已读取 {path}，内容为：{content}")
        elif tool_name == "COUNT_TEXT_CHARS" and "chars" in payload:
            answers.append(f"字符统计结果：{payload['chars']} 个字符。")
        elif tool_name in {"PARSE_DOCUMENT_WITH_MINERU", "MINERU_PARSE_DOCUMENT"}:
            md_path = payload.get("markdown_path") or "未生成 Markdown"
            content_path = payload.get("content_list_v2_path") or "未生成 content_list_v2"
            answers.append(f"文档解析完成。Markdown：{md_path}；结构化结果：{content_path}")

    return answers


def _wants_content_summary(user_input: str) -> bool:
    lowered = user_input.lower()
    keywords = {
        "总结",
        "摘要",
        "概括",
        "主要内容",
        "关键事实",
        "关键结论",
        "结论",
        "待办",
        "提炼",
        "梳理",
        "summary",
        "summarize",
    }
    return any(keyword in lowered for keyword in keywords)


def _summarize_read_content(*, path: str, content: str, user_input: str) -> str:
    if not content.strip():
        return f"已读取 {path}，但文件内容为空，无法生成摘要。"

    prompt = f"""
你是离线边缘端 Agent 的文档总结器。
请严格根据文件内容回答用户请求，不要编造文件中没有的信息。
如果文件内容中包含用户要求的固定输出格式或固定句子，请优先遵循用户请求。

用户请求：
{user_input}

文件路径：
{path}

文件内容：
{content[:12000]}

请用中文输出最终结果。不要输出工具调用过程，不要输出 Action/Observation。
""".strip()
    return llm_call(prompt).strip()


def _json_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
