from __future__ import annotations

from pathlib import Path
from typing import Any

from . import context_store


MAX_CONTEXT_PACK_CHARS = 8000


def build_context_pack(
    transition: dict[str, Any],
    *,
    user_message: str,
    max_chars: int = MAX_CONTEXT_PACK_CHARS,
) -> str:
    if not transition.get("should_attach_context"):
        return ""
    context_id = str(transition.get("target_context_id") or "")
    if not context_id:
        return ""

    context = context_store.get_context(context_id, include_artifacts=True, include_chunks=False)
    if not context:
        return ""
    chunks = context_store.search_chunks(user_message, context_id=context_id, limit=8)
    if not chunks:
        stored = context_store.get_context(context_id, include_artifacts=True, include_chunks=True) or context
        chunks = list(stored.get("chunks") or [])[:8]

    lines = [
        "<focus_context>",
        f"state: {transition.get('to_state')}",
        f"context_id: {context['id']}",
        f"kind: {context['kind']}",
        f"title: {context['title']}",
        f"summary: {context.get('summary') or 'N/A'}",
        f"source_path: {context.get('source_path') or 'N/A'}",
        "artifacts:",
    ]
    for artifact in context.get("artifacts") or []:
        lines.append(
            f"- {artifact.get('artifact_type')}: {artifact.get('path')} ({artifact.get('name') or Path(str(artifact.get('path'))).name})"
        )

    lines.append("relevant_chunks:")
    remaining = max_chars - sum(len(line) + 1 for line in lines) - len("</focus_context>")
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        prefix = f"- chunk {index} [{chunk.get('chunk_type', 'text')}]: "
        allowed = max(0, remaining - len(prefix) - 1)
        if allowed <= 0:
            break
        if len(text) > allowed:
            text = text[: max(0, allowed - 20)] + "\n[truncated]"
        lines.append(prefix + text)
        remaining -= len(prefix) + len(text) + 1
        if remaining <= 0:
            break
    lines.append("</focus_context>")
    return "\n".join(lines)
