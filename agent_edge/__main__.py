from __future__ import annotations

import argparse
import json
import os
import sys

from .graph import run_agent, user_visible_response
from .llm import DEFAULT_MODEL, DEFAULT_OLLAMA_BASE_URL
from .paths import ensure_demo_assets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线 Edge LangGraph Agent")
    parser.add_argument("prompt", nargs="*", help="用户任务")
    parser.add_argument(
        "--backend",
        choices=["ollama", "mock"],
        default=os.environ.get("AGENT_LLM_BACKEND", "ollama"),
        help="LLM 后端，默认 ollama",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
        help=f"Ollama 模型名，默认 {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        help=f"Ollama API 地址，默认 {DEFAULT_OLLAMA_BASE_URL}",
    )
    parser.add_argument("--show-trace", action="store_true", help="显示 plan 和 past_steps")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    user_input = " ".join(args.prompt).strip() or "请读取 demo_input.txt，并统计我的输入长度。"

    os.environ["AGENT_LLM_BACKEND"] = args.backend
    os.environ["OLLAMA_MODEL"] = args.model
    os.environ["OLLAMA_BASE_URL"] = args.base_url

    ensure_demo_assets()

    try:
        result = run_agent(user_input)
    except Exception as exc:
        print(f"Agent 运行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        if args.backend == "ollama":
            print(
                "提示：请确认 Ollama 正在运行，并已执行 `ollama pull qwen2.5:1.5b`。",
                file=sys.stderr,
            )
        return 1

    print(user_visible_response(result))

    if args.show_trace:
        print("\n===== Remaining Plan =====")
        print(json.dumps(result["plan"], ensure_ascii=False, indent=2, default=str))
        print("\n===== Past Steps =====")
        print(json.dumps(result["past_steps"], ensure_ascii=False, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
