from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .heavy_runtime import ManagedProcessError, create_resource_token, run_ocr_blocking
from .ocr_memory import record_ocr_result
from .paths import PROJECT_ROOT, WORKSPACE_DIR, safe_child_path


SUPPORTED_OCR_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
DEFAULT_OCR_RESPONSE_TEXT_CHARS = 12000


def parse_document_with_ocr_pc(args: dict[str, Any]) -> dict[str, Any]:
    rel_path = str(args.get("path", "")).strip()
    input_path = safe_child_path(WORKSPACE_DIR, rel_path)
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if input_path.suffix.lower() not in SUPPORTED_OCR_SUFFIXES:
        raise ValueError(f"Unsupported OCR document type: {input_path.suffix}")

    output_root = _resolve_output_root(args)
    output_root.mkdir(parents=True, exist_ok=True)

    task_id = str(args.get("task_id") or uuid.uuid4().hex[:12])
    token = create_resource_token(task_id, "OCR_RUNNING")
    timeout_seconds = float(args.get("timeout_seconds") or os.environ.get("OCR_PC_TIMEOUT_SECONDS", "1800"))
    restart_llama = bool(args.get("restart_llama", True))
    callback_url = str(
        args.get("callback_url")
        or os.environ.get("AGENT_RESOURCE_CALLBACK_URL")
        or "http://127.0.0.1:7860/api/runtime/resource"
    )

    log_path = output_root / "_logs" / f"{input_path.stem}-{int(time.time())}.log"
    result_path = output_root / f"{input_path.stem}_ocr_result.json"
    command = [
        _python_for_ocr(),
        "-m",
        "agent_edge.ocr_pc_runner",
        "--input",
        str(input_path),
        "--output-root",
        str(output_root),
        "--task-id",
        task_id,
        "--token",
        token,
        "--callback-url",
        callback_url,
    ]

    env = os.environ.copy()
    env.setdefault("OCR_PC_PROJECT_DIR", str(PROJECT_ROOT / "OCR_pc" / "OCR_pc"))

    try:
        result = run_ocr_blocking(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            restart_llama=restart_llama,
            token=token,
            task_id=task_id,
        )
    except ManagedProcessError as exc:
        payload = _read_result_payload(result_path)
        return {
            "ok": False,
            "error": payload.get("error") or str(exc),
            "log_path": str(exc.log_path or log_path),
            "log_tail": exc.log_tail,
            "result_path": str(result_path),
        }

    payload = _read_result_payload(result_path)
    if not payload.get("ok"):
        return {
            "ok": False,
            "error": payload.get("error") or "OCR runner did not produce a successful result",
            "log_path": str(result.log_path),
            "log_tail": result.log_tail,
            "result_path": str(result_path),
        }

    payload.update(
        {
            "ok": True,
            "input_path": rel_path,
            "output_root": str(output_root),
            "backend": "ocr_pc",
            "log_path": str(result.log_path),
        }
    )
    _attach_markdown_text(payload)
    record_ocr_result(task_id=task_id, payload=payload, source_path=rel_path)
    return payload


def _resolve_output_root(args: dict[str, Any]) -> Path:
    output_arg = str(args.get("output_dir") or "ocr_outputs").strip()
    return safe_child_path(WORKSPACE_DIR, output_arg)


def _python_for_ocr() -> str:
    configured = os.environ.get("OCR_PC_PYTHON")
    if configured:
        return str(Path(configured).expanduser())

    windows_venv = PROJECT_ROOT / ".runtime" / "ocr_pc_venv" / "Scripts" / "python.exe"
    if os.name == "nt" and windows_venv.exists():
        return str(windows_venv)

    return sys.executable


def _read_result_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"OCR result JSON parse failed: {exc}"}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "OCR result is not an object"}


def _attach_markdown_text(payload: dict[str, Any]) -> None:
    markdown_path = Path(str(payload.get("markdown_path") or ""))
    if not markdown_path.exists() or not markdown_path.is_file():
        return
    text = markdown_path.read_text(encoding="utf-8", errors="replace")
    max_chars = int(os.environ.get("OCR_PC_RESPONSE_TEXT_CHARS", str(DEFAULT_OCR_RESPONSE_TEXT_CHARS)))
    payload["ocr_text_path"] = str(markdown_path)
    payload["ocr_text_chars"] = len(text)
    payload["ocr_text_truncated"] = len(text) > max_chars
    payload["ocr_text"] = text[:max_chars]
