from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from .heavy_runtime import ManagedProcessError, run_mineru_blocking
from .paths import PROJECT_ROOT, WORKSPACE_DIR, safe_child_path


SUPPORTED_DOCUMENT_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".docx",
    ".pptx",
    ".xlsx",
}


def parse_document_with_mineru(args: dict[str, Any]) -> dict[str, Any]:
    rel_path = str(args.get("path", "")).strip()
    input_path = safe_child_path(WORKSPACE_DIR, rel_path)
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if input_path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ValueError(f"Unsupported document type: {input_path.suffix}")

    output_root = _resolve_output_root(args)
    output_root.mkdir(parents=True, exist_ok=True)

    backend = str(args.get("backend") or os.environ.get("MINERU_BACKEND", "pipeline"))
    method = str(args.get("method") or os.environ.get("MINERU_METHOD", "auto"))
    lang = str(args.get("lang") or os.environ.get("MINERU_LANG", "ch"))
    timeout_seconds = float(args.get("timeout_seconds") or os.environ.get("MINERU_TIMEOUT_SECONDS", "1800"))
    restart_llama = bool(args.get("restart_llama", True))

    log_path = output_root / "_logs" / f"{input_path.stem}-{int(time.time())}.log"
    command = [
        sys.executable,
        "-m",
        "mineru.cli.client",
        "-p",
        str(input_path),
        "-o",
        str(output_root),
        "-b",
        backend,
        "-m",
        method,
        "-l",
        lang,
    ]

    env = os.environ.copy()
    env.setdefault("MINERU_API_MAX_CONCURRENT_REQUESTS", "1")
    env.setdefault("MINERU_PROCESSING_WINDOW_SIZE", "8")
    env.setdefault("MINERU_DEVICE_MODE", "cpu")
    env.setdefault("MINERU_LOG_LEVEL", "INFO")
    if args.get("formula") is not None:
        env["MINERU_FORMULA_ENABLE"] = _bool_env(args["formula"])
    if args.get("table") is not None:
        env["MINERU_TABLE_ENABLE"] = _bool_env(args["table"])

    mineru_project_dir = Path(
        os.environ.get("MINERU_PROJECT_DIR", str(PROJECT_ROOT / "mineru"))
    ).expanduser()
    cwd = mineru_project_dir if mineru_project_dir.exists() else PROJECT_ROOT

    try:
        result = run_mineru_blocking(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            restart_llama=restart_llama,
        )
    except ManagedProcessError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "log_path": str(exc.log_path or log_path),
            "log_tail": exc.log_tail,
        }

    artifacts = _find_artifacts(output_root, input_path.stem)
    artifacts.update(
        {
            "ok": True,
            "input_path": rel_path,
            "output_root": str(output_root),
            "backend": backend,
            "method": method,
            "lang": lang,
            "log_path": str(result.log_path),
        }
    )
    return artifacts


def _resolve_output_root(args: dict[str, Any]) -> Path:
    output_arg = str(args.get("output_dir") or "mineru_outputs").strip()
    return safe_child_path(WORKSPACE_DIR, output_arg)


def _find_artifacts(output_root: Path, stem: str) -> dict[str, Any]:
    md_path = _first_existing(output_root.rglob(f"{stem}.md"))
    content_v2_path = _first_existing(output_root.rglob(f"{stem}_content_list_v2.json"))
    content_path = _first_existing(output_root.rglob(f"{stem}_content_list.json"))
    middle_path = _first_existing(output_root.rglob(f"{stem}_middle.json"))
    images_dir = _first_existing(path for path in output_root.rglob("images") if path.is_dir())

    preview = ""
    if md_path is not None:
        preview = _read_preview(md_path)

    return {
        "markdown_path": str(md_path) if md_path else None,
        "content_list_v2_path": str(content_v2_path) if content_v2_path else None,
        "content_list_path": str(content_path) if content_path else None,
        "middle_json_path": str(middle_path) if middle_path else None,
        "images_dir": str(images_dir) if images_dir else None,
        "markdown_preview": preview,
    }


def _first_existing(paths: Any) -> Path | None:
    for path in paths:
        return Path(path)
    return None


def _read_preview(path: Path) -> str:
    limit = int(os.environ.get("MINERU_MARKDOWN_PREVIEW_CHARS", "6000"))
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def _bool_env(value: Any) -> str:
    return "true" if bool(value) else "false"
