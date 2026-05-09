from __future__ import annotations

import json
import re
from typing import Any, Tuple


def extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_json_list(text: str) -> list[dict[str, Any]]:
    """从模型输出中提取第一个 JSON list。"""
    cleaned = strip_markdown_fence(text)
    decoder = json.JSONDecoder()

    for idx, char in enumerate(cleaned):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value

    raise ValueError(f"没有解析到 JSON list：{text[:500]}")


def parse_react_output(text: str) -> Tuple[str, str, str]:
    """解析 Thought / Action / Action Input 格式。"""
    cleaned = strip_markdown_fence(text)

    thought_match = re.search(r"^Thought:\s*(.*?)$", cleaned, flags=re.MULTILINE)
    action_match = re.search(r"^Action:\s*(.*?)$", cleaned, flags=re.MULTILINE)
    input_match = re.search(r"^Action Input:\s*(.*)$", cleaned, flags=re.MULTILINE | re.DOTALL)

    if not action_match:
        raise ValueError(f"ReAct 输出缺少 Action：{text[:500]}")

    thought = thought_match.group(1).strip() if thought_match else ""
    raw_action = action_match.group(1).strip().upper()
    action = ""
    for candidate in ("READ_SKILL", "USE_TOOL", "FINISH"):
        if re.search(rf"\b{candidate}\b", raw_action):
            action = candidate
            break
    if not action:
        raise ValueError(f"ReAct 输出包含未知 Action：{raw_action}")

    action_input = input_match.group(1).strip() if input_match else ""
    action_input = strip_markdown_fence(action_input)

    return thought, action, action_input


def strip_route_marker(text: str, route_prefix: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith(route_prefix):
        return "\n".join(lines[1:]).strip()
    return text.strip()
