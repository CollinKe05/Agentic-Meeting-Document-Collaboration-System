from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import task_store
from .llm import llm_call
from .ocr_memory import read_latest_ocr_result
from .paths import WORKSPACE_DIR, safe_child_path


MAX_OCR_SUMMARY_CHARS = int(os.environ.get("OCR_SUMMARY_EXPORT_MAX_CHARS", "24000"))


def export_ocr_summary(args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id") or "").strip()
    markdown_path, metadata = _resolve_ocr_markdown(args, task_id=task_id)
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    if not markdown.strip():
        raise ValueError(f"OCR Markdown is empty: {markdown_path}")

    summary = _generate_summary(markdown=markdown, markdown_path=markdown_path, metadata=metadata)
    output_dir = _output_dir(markdown_path=markdown_path, task_id=task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "ocr_summary.json"
    markdown_summary_path = output_dir / "ocr_summary.md"
    typ_path = output_dir / "ocr_summary.typ"
    source_copy_path = output_dir / "ocr_source.md"
    pdf_path = output_dir / "ocr_summary.pdf"

    source_copy_path.write_text(markdown, encoding="utf-8", newline="\n")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    markdown_summary_path.write_text(_render_markdown(summary), encoding="utf-8", newline="\n")
    typ_path.write_text(_render_typst(summary), encoding="utf-8", newline="\n")
    typst_result = _compile_typst(typ_path=typ_path, pdf_path=pdf_path)

    artifact_id = f"{task_id or 'latest'}:ocr_summary:{hashlib.sha1(str(output_dir).encode()).hexdigest()[:10]}"
    task_store.record_artifact(
        artifact_id,
        task_id=task_id or None,
        kind="ocr_summary_export",
        path=_workspace_rel(markdown_summary_path),
        name=markdown_summary_path.name,
        metadata={
            "output_dir": _workspace_rel(output_dir),
            "json_path": _workspace_rel(json_path),
            "markdown_path": _workspace_rel(markdown_summary_path),
            "typ_path": _workspace_rel(typ_path),
            "pdf_path": _workspace_rel(pdf_path) if typst_result["ok"] else "",
            "source_markdown_path": _workspace_rel(markdown_path),
            "source_copy_path": _workspace_rel(source_copy_path),
        },
    )

    return {
        "ok": True,
        "title": summary.get("title"),
        "summary": summary.get("summary"),
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(markdown_summary_path),
        "typ_path": str(typ_path),
        "pdf_path": str(pdf_path) if typst_result["ok"] else None,
        "source_markdown_path": str(markdown_path),
        "source_copy_path": str(source_copy_path),
        "typst": typst_result,
        "source_chars": len(markdown),
        "metadata": metadata,
    }


def _resolve_ocr_markdown(args: dict[str, Any], *, task_id: str) -> tuple[Path, dict[str, Any]]:
    rel_path = str(args.get("path") or args.get("markdown_path") or "").strip()
    if rel_path:
        path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
        return path, {"source": "explicit_path", "markdown_path": rel_path}

    artifact = task_store.latest_task_artifact(task_id, kind="ocr_result") if task_id else None
    if not artifact:
        artifact = task_store.latest_artifact(kind="ocr_result")
    if artifact:
        rel_path = str(artifact.get("path") or "")
        path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
        return path, artifact.get("metadata") or {}

    latest = read_latest_ocr_result({})
    rel_path = str(latest.get("path") or "")
    path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
    return path, latest.get("metadata") or {}


def _generate_summary(*, markdown: str, markdown_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是离线端 OCR 文档总结器。请严格基于 OCR 原文生成结构化总结，不要编造原文没有的信息。

输出必须是 JSON object，不要 Markdown，不要代码块。字段：
- title: 文档标题或最接近的主题
- summary: 200-500 字中文摘要
- key_points: 6-12 条关键事实
- conclusions: 3-8 条结论或可确认信息
- action_items: 待办事项数组；没有就 []
- risks: OCR 噪声、缺页、信息不完整、需要复核之处
- source_notes: 对原文来源和 OCR 质量的简短说明

OCR Markdown 路径：
{markdown_path}

OCR 元数据：
{json.dumps(metadata, ensure_ascii=False, default=str)}

OCR 原文：
{markdown[:MAX_OCR_SUMMARY_CHARS]}
""".strip()
    try:
        data = _extract_json_object(llm_call(prompt))
    except Exception as exc:  # noqa: BLE001 - export should still produce files
        data = _fallback_summary(markdown, markdown_path=markdown_path, error=f"{type(exc).__name__}: {exc}")
    return _normalize_summary(data, markdown=markdown, markdown_path=markdown_path)


def _fallback_summary(markdown: str, *, markdown_path: Path, error: str) -> dict[str, Any]:
    lines = _content_lines(markdown)
    title = next((line.lstrip("#").strip() for line in lines if line.startswith("#")), markdown_path.stem)
    return {
        "title": title or markdown_path.stem,
        "summary": "LLM 未能完成 OCR 总结，已基于 OCR 原文生成抽取式摘要。错误：" + error,
        "key_points": lines[:10],
        "conclusions": lines[:5],
        "action_items": [],
        "risks": ["LLM 总结失败，当前结果为抽取式摘要，需要人工复核。"],
        "source_notes": f"Source OCR markdown: {markdown_path}",
    }


def _normalize_summary(data: dict[str, Any], *, markdown: str, markdown_path: Path) -> dict[str, Any]:
    fallback = _fallback_summary(markdown, markdown_path=markdown_path, error="")
    title = str(data.get("title") or fallback["title"]).strip() or markdown_path.stem
    return {
        "schema_version": "ocr_summary_v1",
        "title": title,
        "source_markdown_path": str(markdown_path),
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": str(data.get("summary") or fallback["summary"]).strip(),
        "key_points": _string_list(data.get("key_points")) or fallback["key_points"],
        "conclusions": _string_list(data.get("conclusions")) or fallback["conclusions"],
        "action_items": _string_list(data.get("action_items")),
        "risks": _string_list(data.get("risks")) or fallback["risks"],
        "source_notes": str(data.get("source_notes") or fallback["source_notes"]).strip(),
        "source_excerpt": markdown[:4000],
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['title']}",
        "",
        "## 摘要",
        str(summary.get("summary") or "暂无摘要。"),
        "",
        "## 关键事实",
        *_markdown_list(summary.get("key_points"), empty="暂无关键事实。"),
        "",
        "## 结论",
        *_markdown_list(summary.get("conclusions"), empty="暂无明确结论。"),
        "",
        "## 待办事项",
        *_markdown_list(summary.get("action_items"), empty="暂无待办事项。"),
        "",
        "## 风险与复核",
        *_markdown_list(summary.get("risks"), empty="暂无风险。"),
        "",
        "## 来源",
        f"- OCR Markdown：{summary.get('source_markdown_path')}",
        f"- 生成时间：{summary.get('generated_at')}",
        f"- 说明：{summary.get('source_notes')}",
        "",
    ]
    return "\n".join(lines)


def _render_typst(summary: dict[str, Any]) -> str:
    return f"""#set document(title: [{_typst_escape(summary['title'])}])
#set page(margin: 1.8cm)
#set text(font: \"Noto Sans CJK SC\", size: 10.5pt)

= {_typst_escape(summary['title'])}

== 摘要
{_typst_escape(summary.get('summary') or '暂无摘要。')}

== 关键事实
{_typst_bullets(summary.get('key_points'), empty='暂无关键事实。')}

== 结论
{_typst_bullets(summary.get('conclusions'), empty='暂无明确结论。')}

== 待办事项
{_typst_bullets(summary.get('action_items'), empty='暂无待办事项。')}

== 风险与复核
{_typst_bullets(summary.get('risks'), empty='暂无风险。')}

== 来源
- OCR Markdown：{_typst_escape(summary.get('source_markdown_path') or '')}
- 生成时间：{_typst_escape(summary.get('generated_at') or '')}
- 说明：{_typst_escape(summary.get('source_notes') or '')}
"""


def _compile_typst(*, typ_path: Path, pdf_path: Path) -> dict[str, Any]:
    typst_bin = os.environ.get("TYPST_BIN") or shutil.which("typst")
    runtime_typst = WORKSPACE_DIR.parent / ".runtime" / "bin" / ("typst.exe" if os.name == "nt" else "typst")
    if not typst_bin and runtime_typst.exists():
        typst_bin = str(runtime_typst)
    if not typst_bin:
        return {"ok": False, "compiled": False, "error": "typst command not found; JSON/Markdown/Typst files were generated."}
    try:
        subprocess.run(
            [typst_bin, "compile", str(typ_path), str(pdf_path)],
            cwd=str(typ_path.parent),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return {"ok": True, "compiled": True, "path": str(pdf_path)}
    except Exception as exc:  # noqa: BLE001 - keep non-PDF outputs
        return {"ok": False, "compiled": False, "error": f"{type(exc).__name__}: {exc}"}


def _output_dir(*, markdown_path: Path, task_id: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    source = re.sub(r"[^A-Za-z0-9_.-]+", "_", markdown_path.stem).strip("_") or "ocr"
    suffix = task_id[:8] if task_id else hashlib.sha1(str(markdown_path).encode()).hexdigest()[:8]
    return WORKSPACE_DIR / "ocr_summary_outputs" / f"{stamp}_{source}_{suffix}"


def _content_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in markdown.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line or set(line) <= {"=", "-", "_", "*"}:
            continue
        lines.append(line)
    return lines


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("task") or item.get("title") or item.get("content")
            else:
                text = item
            normalized = str(text or "").strip()
            if normalized:
                result.append(normalized)
        return result
    return [str(value).strip()] if str(value).strip() else []


def _markdown_list(items: Any, *, empty: str) -> list[str]:
    values = _string_list(items)
    return [f"- {item}" for item in values] if values else [empty]


def _typst_bullets(items: Any, *, empty: str) -> str:
    values = _string_list(items)
    if not values:
        return _typst_escape(empty)
    return "\n".join(f"- {_typst_escape(item)}" for item in values)


def _typst_escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("#", "\\#").replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"LLM did not return a JSON object: {raw[:300]}")


def _workspace_rel(path: Path | str) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(WORKSPACE_DIR.resolve()).as_posix()
    except ValueError:
        return str(candidate)
