from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import task_store
from .paths import WORKSPACE_DIR, safe_child_path


DEFAULT_OCR_CONTEXT_CHARS = 24000


def record_ocr_result(*, task_id: str, payload: dict[str, Any], source_path: str) -> None:
    markdown_path = str(payload.get("markdown_path") or "")
    if not markdown_path:
        return

    rel_markdown = _to_workspace_relative(markdown_path)
    metadata = {
        "source_path": source_path,
        "markdown_path": rel_markdown,
        "content_list_v2_path": _to_workspace_relative(str(payload.get("content_list_v2_path") or "")),
        "blocks_json_path": _to_workspace_relative(str(payload.get("blocks_json_path") or "")),
        "images_dir": _to_workspace_relative(str(payload.get("images_dir") or "")),
        "block_count": payload.get("block_count"),
        "backend": payload.get("backend", "ocr_pc"),
    }
    artifact_id = f"{task_id}:ocr:{Path(rel_markdown).stem}"
    task_store.record_artifact(
        artifact_id,
        task_id=task_id,
        kind="ocr_result",
        path=rel_markdown,
        name=Path(rel_markdown).name,
        metadata=metadata,
    )


def read_latest_ocr_result(args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    max_chars = int(args.get("max_chars") or os.environ.get("AGENT_MAX_OCR_CONTEXT_CHARS", str(DEFAULT_OCR_CONTEXT_CHARS)))
    rel_path = str(args.get("path") or "").strip()

    metadata: dict[str, Any] = {}
    if rel_path:
        markdown_path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
    else:
        artifact = task_store.latest_artifact(kind="ocr_result")
        if artifact:
            rel_path = str(artifact.get("path") or "")
            metadata = artifact.get("metadata") or {}
            try:
                markdown_path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
            except Exception:
                markdown_path = _latest_markdown_from_outputs()
                rel_path = _to_workspace_relative(str(markdown_path))
                metadata = {}
        else:
            markdown_path = _latest_markdown_from_outputs()
            rel_path = _to_workspace_relative(str(markdown_path))

    if not markdown_path.exists() or not markdown_path.is_file():
        raise FileNotFoundError(str(markdown_path))

    text = markdown_path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    content = text[:max_chars]
    return {
        "ok": True,
        "path": rel_path,
        "content": content,
        "truncated": truncated,
        "chars": len(text),
        "metadata": metadata,
    }


def latest_ocr_result_exists() -> bool:
    artifact = task_store.latest_artifact(kind="ocr_result")
    if artifact:
        try:
            path = safe_child_path(WORKSPACE_DIR, str(artifact.get("path") or ""), expected_suffix=".md")
            if path.is_file():
                return True
        except Exception:
            pass
    try:
        return _latest_markdown_from_outputs().is_file()
    except FileNotFoundError:
        return False


def _latest_markdown_from_outputs() -> Path:
    output_dir = WORKSPACE_DIR / "ocr_outputs"
    candidates = [path for path in output_dir.glob("*.md") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(str(output_dir / "*.md"))
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _to_workspace_relative(path: str) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(WORKSPACE_DIR.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()
