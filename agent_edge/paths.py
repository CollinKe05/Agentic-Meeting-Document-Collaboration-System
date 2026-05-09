from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = Path(os.environ.get("AGENT_SKILLS_DIR", PROJECT_ROOT / "skills")).expanduser()
WORKSPACE_DIR = Path(os.environ.get("AGENT_WORKSPACE_DIR", PROJECT_ROOT / "workspace_files")).expanduser()

MAX_LOCAL_FILE_BYTES = int(os.environ.get("AGENT_MAX_LOCAL_FILE_BYTES", str(64 * 1024)))


def ensure_demo_assets() -> None:
    """补齐 demo 文件，避免新机器首次运行时缺少本地技能或测试文件。"""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    defaults = {
        SKILLS_DIR / "skills_index.md": """# 本地技能索引

可用技能：
- read_file_skill.md：学习如何安全读取本地文本文件。
- local_tool_skill.md：学习可用的本地 dummy 工具。

约束：
- 技能文件必须位于 skills/ 目录下。
- 禁止路径穿越，例如 ../secret.txt。
- 禁止调用云端 API。
""",
        SKILLS_DIR / "read_file_skill.md": """# 安全读取文件技能

推荐动作：

Action: USE_TOOL
Action Input:
{"tool_name": "SAFE_READ_TEXT_FILE", "args": {"path": "demo_input.txt"}}

安全策略：
- 只能读取 workspace_files/ 目录下的文件。
- 使用 pathlib.resolve() 规范化路径。
- 使用 relative_to() 校验目标路径没有逃逸出允许目录。
""",
        SKILLS_DIR / "local_tool_skill.md": """# 本地工具技能

可用本地工具：
- LOCAL_ECHO：回显文本。
- COUNT_TEXT_CHARS：统计文本字符数。
- LIST_SKILLS：列出 skills/ 目录中的 markdown 文件。
- SAFE_READ_TEXT_FILE：读取 workspace_files/ 下的文本文件。
- SAFE_WRITE_TEXT_FILE：写入 workspace_files/ 下的文本文件。
""",
        WORKSPACE_DIR / "demo_input.txt": "这是一个 WSL/Ubuntu/Windows 都可读取的离线 demo 文件。\n",
    }

    for path, content in defaults.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8", newline="\n")


def safe_child_path(base_dir: Path, user_path: str, expected_suffix: str | None = None) -> Path:
    """把用户路径安全地限制在 base_dir 内。

    这里不手写字符串拼接，而是使用 pathlib，兼容 Windows 和 Ubuntu。
    resolve() 会规范化路径，relative_to() 会阻止 ../ 或绝对路径逃逸。
    """
    if not isinstance(user_path, str) or not user_path.strip():
        raise ValueError("路径不能为空")
    if "\x00" in user_path:
        raise ValueError("路径包含非法 NUL 字符")

    base = base_dir.resolve()
    candidate = (base / user_path).resolve()

    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"拒绝访问越界路径：{user_path}") from exc

    if expected_suffix and candidate.suffix.lower() != expected_suffix.lower():
        raise ValueError(f"文件后缀必须是 {expected_suffix}")

    return candidate


def read_limited_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    if path.stat().st_size > MAX_LOCAL_FILE_BYTES:
        raise ValueError(f"文件过大，超过 {MAX_LOCAL_FILE_BYTES} bytes")
    return path.read_text(encoding="utf-8")


def write_limited_text(path: Path, text: str, overwrite: bool = False) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_LOCAL_FILE_BYTES:
        raise ValueError(f"写入内容过大，超过 {MAX_LOCAL_FILE_BYTES} bytes")
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
