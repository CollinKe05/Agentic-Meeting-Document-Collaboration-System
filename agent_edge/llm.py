from __future__ import annotations

import json
import os
from typing import Any

import requests

from .parsing import extract_tag


DEFAULT_MODEL = "qwen2.5:1.5b"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def llm_call(prompt: str) -> str:
    """统一 LLM 入口。

    AGENT_LLM_BACKEND=ollama 时调用本机 Ollama HTTP API。
    AGENT_LLM_BACKEND=mock 时使用确定性 mock，方便无模型环境调试图逻辑。
    """
    backend = os.environ.get("AGENT_LLM_BACKEND", "ollama").strip().lower()
    if backend == "mock":
        return mock_llm_call(prompt)
    if backend == "ollama":
        return ollama_generate(prompt)
    raise ValueError(f"未知 LLM 后端：{backend}")


def ollama_generate(prompt: str) -> str:
    model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

    response = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": 4096,
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return str(payload.get("response", "")).strip()


def mock_llm_call(prompt: str) -> str:
    """确定性 mock，本地调试用，不访问网络。"""
    if "[PLANNER]" in prompt:
        user_input = extract_tag(prompt, "user_input")
        return json.dumps(_fallback_plan(user_input), ensure_ascii=False)

    if "[EXECUTOR]" in prompt:
        task = json.loads(extract_tag(prompt, "current_task_json"))

        if int(task.get("attempts", 0)) >= 3:
            return (
                "Thought: 当前步骤已经达到最大尝试次数，为避免无限循环，结束该步骤。\n"
                "Action: FINISH\n"
                "Action Input: 步骤达到最大尝试次数。"
            )

        last_observation = str(task.get("last_observation", ""))
        if last_observation:
            return (
                "Thought: 我已经拿到 Observation，可以完成当前步骤。\n"
                "Action: FINISH\n"
                f"Action Input: 当前步骤完成。Observation 摘要：{last_observation[:260]}"
            )

        if task.get("kind") == "learn_skill":
            return (
                "Thought: 当前任务需要读取本地 markdown 技能文件。\n"
                "Action: READ_SKILL\n"
                f"Action Input: {task.get('skill_file', 'skills_index.md')}"
            )

        if task.get("kind") == "use_tool":
            payload = {
                "tool_name": task.get("tool_name"),
                "args": task.get("tool_input", {}),
            }
            return (
                "Thought: 当前任务需要执行一个本地工具。\n"
                "Action: USE_TOOL\n"
                f"Action Input: {json.dumps(payload, ensure_ascii=False)}"
            )

        return (
            "Thought: 无法识别任务类型，保守结束。\n"
            "Action: FINISH\n"
            "Action Input: 未识别任务类型。"
        )

    return (
        "Thought: 未识别 prompt 类型。\n"
        "Action: FINISH\n"
        "Action Input: 无操作。"
    )


def _fallback_plan(user_input: str) -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "kind": "learn_skill",
            "objective": "读取技能索引，建立本地工具地图",
            "skill_file": "skills_index.md",
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 2,
            "kind": "learn_skill",
            "objective": "学习安全读取本地文件的技能说明",
            "skill_file": "read_file_skill.md",
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 3,
            "kind": "use_tool",
            "objective": "读取本地 demo_input.txt 文件",
            "tool_name": "SAFE_READ_TEXT_FILE",
            "tool_input": {"path": "demo_input.txt"},
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 4,
            "kind": "use_tool",
            "objective": "统计用户输入字符数",
            "tool_name": "COUNT_TEXT_CHARS",
            "tool_input": {"text": user_input},
            "status": "todo",
            "attempts": 0,
        },
    ]


def fallback_plan(user_input: str) -> list[dict[str, Any]]:
    return _fallback_plan(user_input)
