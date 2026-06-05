"""Ollama LLM 客户端 — 4种模式"""
import os
import re
import time
from pathlib import Path

from .prompts import get_prompt, MODE_SUFFIX


def _read_markdown(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 去除图片引用，避免 API 阻塞
    content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
    return content.strip()


def _strip_proxy():
    """临时移除代理环境变量，避免 ollama 连接问题"""
    proxy_vars = [
        "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
        "ALL_PROXY", "all_proxy", "ftp_proxy", "FTP_PROXY",
    ]
    saved = {}
    for var in proxy_vars:
        if var in os.environ:
            saved[var] = os.environ.pop(var)
    return saved


def _restore_proxy(saved: dict):
    for var, value in saved.items():
        os.environ[var] = value


class LLMClient:
    def __init__(self, model: str = "qwen2.5:1.5b"):
        self.model = model

    def process(self, input_path: str, output_path: str = "",
                mode: str = "summary", direction: str = "zh2en") -> dict:
        """处理文档，返回 {output_file, elapsed, model}"""
        if not os.path.exists(input_path):
            return {"error": f"文件不存在: {input_path}"}

        content = _read_markdown(input_path)
        if not content:
            return {"error": "文档内容为空"}

        prompt_info = get_prompt(mode, direction)
        messages = [
            {"role": "system", "content": prompt_info["system"]},
            {"role": "user", "content": content},
        ]

        # 解决 ollama 代理问题
        saved = _strip_proxy()
        try:
            import ollama
        finally:
            _restore_proxy(saved)

        print(f"[LLM] 调用 {self.model}，模式: {mode}，内容: {len(content)} 字符")
        t0 = time.time()
        response = ollama.chat(model=self.model, messages=messages)
        elapsed = time.time() - t0
        result_text = response["message"]["content"]
        print(f"[LLM] 完成，耗时 {elapsed:.1f}s，输出 {len(result_text)} 字符")

        # 确定输出路径
        if not output_path:
            in_path = Path(input_path)
            if mode == "translate":
                suffix_key = f"translate_{direction}"
            else:
                suffix_key = mode
            suffix = MODE_SUFFIX.get(suffix_key, f"_{mode}")
            output_path = str(in_path.parent / f"{in_path.stem}{suffix}.md")

        # 写入输出
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(result_text)

        return {"output_file": str(out), "elapsed": round(elapsed, 1), "model": self.model}
