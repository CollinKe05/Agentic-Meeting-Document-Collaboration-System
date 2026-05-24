from __future__ import annotations

import argparse
import json
import os
import sys

from .heavy_runtime import (
    DEFAULT_LLAMA_CPP_BASE_URL,
    DEFAULT_LLAMA_CPP_CTX_SIZE,
    DEFAULT_LLAMA_CPP_MODEL,
    DEFAULT_LLAMA_CPP_MODEL_PATH,
    DEFAULT_LLAMA_CPP_THREADS,
    cleanup_managed_processes,
    ensure_llama_server_running,
)
from .paths import ensure_demo_assets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线边缘端 LangGraph Agent")
    parser.add_argument("prompt", nargs="*", help="用户任务")
    parser.add_argument(
        "--model",
        default=os.environ.get("LLAMA_CPP_MODEL", DEFAULT_LLAMA_CPP_MODEL),
        help=f"llama.cpp 模型别名，默认 {DEFAULT_LLAMA_CPP_MODEL}",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LLAMA_CPP_BASE_URL", DEFAULT_LLAMA_CPP_BASE_URL),
        help=f"llama.cpp OpenAI-compatible API 地址，默认 {DEFAULT_LLAMA_CPP_BASE_URL}",
    )
    parser.add_argument(
        "--model-path",
        default=os.environ.get("LLAMA_CPP_MODEL_PATH", str(DEFAULT_LLAMA_CPP_MODEL_PATH)),
        help="Qwen GGUF 模型文件路径",
    )
    parser.add_argument(
        "--llama-bin",
        default=os.environ.get("LLAMA_CPP_BIN", ""),
        help="llama-server 路径。未指定时使用 .runtime/llama.cpp/build/bin/llama-server。",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("LLAMA_CPP_THREADS", str(DEFAULT_LLAMA_CPP_THREADS))),
        help=f"llama.cpp CPU 线程数，默认 {DEFAULT_LLAMA_CPP_THREADS}",
    )
    parser.add_argument(
        "--ctx-size",
        type=int,
        default=int(os.environ.get("LLAMA_CPP_CTX_SIZE", str(DEFAULT_LLAMA_CPP_CTX_SIZE))),
        help=f"llama.cpp 上下文长度，默认 {DEFAULT_LLAMA_CPP_CTX_SIZE}",
    )
    parser.add_argument("--show-trace", action="store_true", help="显示 plan 和 past_steps")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    user_input = " ".join(args.prompt).strip() or "请读取 demo_input.txt，并统计我的输入长度。"

    os.environ["LLAMA_CPP_MODEL"] = args.model
    os.environ["LLAMA_CPP_BASE_URL"] = args.base_url
    os.environ["LLAMA_CPP_MODEL_PATH"] = args.model_path
    os.environ["LLAMA_CPP_THREADS"] = str(args.threads)
    os.environ["LLAMA_CPP_CTX_SIZE"] = str(args.ctx_size)
    if args.llama_bin:
        os.environ["LLAMA_CPP_BIN"] = args.llama_bin

    ensure_demo_assets()

    try:
        ensure_llama_server_running()
        from .graph import run_agent, user_visible_response

        result = run_agent(user_input)
    except Exception as exc:
        print(f"Agent 运行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "提示：请先运行 scripts/ensure_llama_cpp_wsl.sh，或设置 LLAMA_CPP_BIN 和 LLAMA_CPP_MODEL_PATH。",
            file=sys.stderr,
        )
        return 1
    finally:
        cleanup_managed_processes()

    print(user_visible_response(result))

    if args.show_trace:
        print("\n===== 剩余计划 =====")
        print(json.dumps(result["plan"], ensure_ascii=False, indent=2, default=str))
        print("\n===== 执行历史 =====")
        print(json.dumps(result["past_steps"], ensure_ascii=False, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
