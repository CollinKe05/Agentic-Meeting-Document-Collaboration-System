from __future__ import annotations

import os
from typing import Any

import requests

from .heavy_runtime import (
    DEFAULT_LLAMA_CPP_MODEL,
    ensure_llama_server_running,
    get_llama_cpp_base_url,
    get_llama_cpp_model,
    llm_request_guard,
)


DEFAULT_MODEL = DEFAULT_LLAMA_CPP_MODEL


def llm_call(prompt: str) -> str:
    """统一 LLM 入口。当前项目只允许 llama.cpp。"""
    return llama_cpp_chat(prompt)


def llama_cpp_chat(prompt: str) -> str:
    ensure_llama_server_running()
    timeout = float(os.environ.get("LLAMA_CPP_TIMEOUT_SECONDS", "180"))
    max_tokens = int(os.environ.get("LLAMA_CPP_MAX_TOKENS", "768"))
    base_url = get_llama_cpp_base_url()

    with llm_request_guard():
        response = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": get_llama_cpp_model(),
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0,
                "top_p": 0.9,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        response.raise_for_status()

    payload: dict[str, Any] = response.json()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"llama.cpp 响应缺少 choices：{payload}")

    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError(f"llama.cpp choice 不是 object：{first}")

    message = first.get("message")
    if isinstance(message, dict):
        return str(message.get("content", "")).strip()
    return str(first.get("text", "")).strip()

def _fallback_plan(user_input: str) -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "kind": "learn_skill",
            "objective": "读取本地技能索引，建立工具地图。",
            "skill_file": "skills_index.md",
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 2,
            "kind": "learn_skill",
            "objective": "学习如何安全使用本地工具。",
            "skill_file": "local_tool_skill.md",
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 3,
            "kind": "use_tool",
            "objective": "读取本地 demo 文件。",
            "tool_name": "SAFE_READ_TEXT_FILE",
            "tool_input": {"path": "demo_input.txt"},
            "status": "todo",
            "attempts": 0,
        },
        {
            "id": 4,
            "kind": "use_tool",
            "objective": "统计用户输入字符数。",
            "tool_name": "COUNT_TEXT_CHARS",
            "tool_input": {"text": user_input},
            "status": "todo",
            "attempts": 0,
        },
    ]


def fallback_plan(user_input: str) -> list[dict[str, Any]]:
    return _fallback_plan(user_input)
