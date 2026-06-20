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


MAX_OCR_SUMMARY_CHARS = int(os.environ.get("OCR_SUMMARY_EXPORT_MAX_CHARS", "6000"))


def export_ocr_summary(args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id") or "").strip()
    source_path, source_metadata = _resolve_ocr_markdown(args, task_id=task_id)
    source_markdown = source_path.read_text(encoding="utf-8", errors="replace")
    if not source_markdown.strip():
        raise ValueError(f"OCR Markdown is empty: {source_path}")

    evidence = _build_evidence_pack(source_markdown, source_path=source_path)
    summary = _generate_summary(evidence=evidence, source_path=source_path, metadata=source_metadata)
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output_dir = _output_dir(markdown_path=source_path, task_id=task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "ocr_summary.json"
    markdown_path = output_dir / "ocr_summary.md"
    typ_path = output_dir / "ocr_summary.typ"
    pdf_path = output_dir / "ocr_summary.pdf"

    report_markdown = _render_markdown(summary, source_path=source_path, generated_at=generated_at)
    markdown_path.write_text(report_markdown, encoding="utf-8", newline="\n")
    typ_path.write_text(_markdown_to_typst(report_markdown, title=summary["title"]), encoding="utf-8", newline="\n")
    typst_result = _compile_typst(typ_path=typ_path, pdf_path=pdf_path)

    metadata = {
        "schema_version": "ocr_summary_metadata_v1",
        "title": summary["title"],
        "generated_at": generated_at,
        "mode": summary["mode"],
        "error": summary.get("error", ""),
        "source_markdown_path": str(source_path),
        "summary_markdown_path": str(markdown_path),
        "typst_path": str(typ_path),
        "pdf_path": str(pdf_path) if typst_result["ok"] else "",
        "source_chars": len(source_markdown),
        "summary_chars": len(report_markdown),
        "summary_preview": _preview(report_markdown),
        "typst": typst_result,
        "source_metadata": source_metadata,
    }
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    artifact_id = f"{task_id or 'latest'}:ocr_summary:{hashlib.sha1(str(output_dir).encode()).hexdigest()[:10]}"
    task_store.record_artifact(
        artifact_id,
        task_id=task_id or None,
        kind="ocr_summary_export",
        path=_workspace_rel(markdown_path),
        name=markdown_path.name,
        metadata={
            "output_dir": _workspace_rel(output_dir),
            "json_path": _workspace_rel(json_path),
            "markdown_path": _workspace_rel(markdown_path),
            "typ_path": _workspace_rel(typ_path),
            "pdf_path": _workspace_rel(pdf_path) if typst_result["ok"] else "",
            "source_markdown_path": _workspace_rel(source_path),
        },
    )

    return {
        "ok": True,
        "title": summary["title"],
        "summary": summary["summary"],
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "typ_path": str(typ_path),
        "pdf_path": str(pdf_path) if typst_result["ok"] else None,
        "source_markdown_path": str(source_path),
        "typst": typst_result,
        "source_chars": len(source_markdown),
        "metadata": source_metadata,
    }


def _resolve_ocr_markdown(args: dict[str, Any], *, task_id: str) -> tuple[Path, dict[str, Any]]:
    rel_path = str(args.get("path") or args.get("markdown_path") or "").strip()
    if rel_path:
        path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
        return path, {"source": "explicit_path", "markdown_path": rel_path}

    artifact = task_store.latest_task_artifact(task_id, kind="ocr_result") if task_id else None
    if task_id and not artifact:
        raise FileNotFoundError(f"当前任务没有可总结的 OCR Markdown，请先完成该文件的 OCR 解析。task_id={task_id}")
    if not artifact:
        artifact = task_store.latest_artifact(kind="ocr_result")
    if artifact:
        rel_path = str(artifact.get("path") or "")
        path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
        return path, artifact.get("metadata") or {}

    if task_id:
        raise FileNotFoundError(f"当前任务没有可总结的 OCR Markdown，请先完成该文件的 OCR 解析。task_id={task_id}")

    latest = read_latest_ocr_result({})
    rel_path = str(latest.get("path") or "")
    path = safe_child_path(WORKSPACE_DIR, rel_path, expected_suffix=".md")
    return path, latest.get("metadata") or {}


def _build_evidence_pack(markdown: str, *, source_path: Path) -> str:
    lines = _content_lines(markdown)
    title = _extract_title(markdown) or source_path.stem
    headings = [line.lstrip("#").strip() for line in lines if line.startswith("#")][:12]
    bullets = [_strip_bullet(line) for line in lines if line[:1] in {"-", "*"} or re.match(r"^\d+[\.\)]", line)][:20]
    body = [line for line in lines if not line.startswith("#") and _strip_bullet(line) not in bullets]
    facts = _rank_representative_lines(body, limit=28)
    abstract = _section_excerpt(markdown, headings=("摘要", "Abstract"), limit=8) or _first_long_paragraphs(markdown, limit=3)
    method = _section_excerpt(markdown, headings=("方法", "Method", "Approach", "Model", "Framework"), limit=10)
    conclusion = _section_excerpt(markdown, headings=("结论", "Conclusion", "Conclusions"), limit=8)
    pack = [
        f"文档标题：{title}",
        "",
        "摘要/Abstract摘录：",
        *[f"- {item}" for item in abstract],
        "",
        "方法/Method摘录：",
        *[f"- {item}" for item in method],
        "",
        "结论/Conclusion摘录：",
        *[f"- {item}" for item in conclusion],
        "",
        "章节线索：",
        *[f"- {item}" for item in headings],
        "",
        "原文项目符号：",
        *[f"- {item}" for item in bullets],
        "",
        "代表性原文句子：",
        *[f"- {item}" for item in facts],
    ]
    return "\n".join(pack)[:MAX_OCR_SUMMARY_CHARS]


def _generate_summary(*, evidence: str, source_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    fallback = _fallback_summary(evidence=evidence, source_path=source_path, error="")
    errors: list[str] = []

    overview: dict[str, Any] = {}
    points: dict[str, Any] = {}
    conclusions: dict[str, Any] = {}
    for label, generator in [
        ("overview", _generate_ocr_overview_with_llm),
        ("points", _generate_ocr_points_with_llm),
        ("conclusions", _generate_ocr_conclusions_with_llm),
    ]:
        try:
            if label == "overview":
                overview = generator(evidence=evidence, source_path=source_path, metadata=metadata)
            else:
                generated = generator(evidence=evidence, source_path=source_path, metadata=metadata)
                if label == "points":
                    points = generated
                else:
                    conclusions = generated
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {type(exc).__name__}: {exc}")

    summary_text = str(overview.get("summary") or fallback["summary"]).strip()
    risk_items = _string_list(conclusions.get("risks")) or _fallback_risks("；".join(errors))
    return {
        "title": str(overview.get("title") or fallback["title"]).strip() or source_path.stem,
        "summary": summary_text,
        "key_points": _string_list(points.get("key_points")) or fallback["key_points"],
        "methods_or_workflow": _string_list(points.get("methods_or_workflow")),
        "conclusions": _string_list(conclusions.get("conclusions")) or fallback["conclusions"],
        "risks": risk_items,
        "mode": "llm_sections_partial" if errors else "llm_sections",
        "error": "；".join(errors),
    }


def _generate_ocr_overview_with_llm(*, evidence: str, source_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是离线端 OCR 文档总结器。这里只生成报告的“概览”部分。

只输出一个 JSON object，不要 Markdown，不要代码块，不要解释。字段：
{{"title":"不超过40字","summary":"80到140字中文摘要"}}

规则：
- 不要编造 evidence 中没有的信息。
- 优先使用“摘要/Abstract摘录”。
- 不要把 Introduction、Related Work、目录标题当摘要。
- 必须在 180 个中文字符内结束。

OCR Markdown 路径：{source_path}
OCR 元数据：{json.dumps(metadata, ensure_ascii=False, default=str)}

evidence:
{evidence}
""".strip()
    return _llm_json_call(prompt)


def _generate_ocr_points_with_llm(*, evidence: str, source_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是离线端 OCR 文档总结器。这里只生成报告的“关键事实”和“方法/流程”部分。

只输出一个 JSON object，不要 Markdown，不要代码块，不要解释。字段：
{{"key_points":["每条不超过45字，4到6条"],"methods_or_workflow":["每条不超过45字，0到5条"]}}

规则：
- 不要编造 evidence 中没有的信息。
- 不要写“第几页”“文档内容”等泛泛内容。
- 优先使用“方法/Method摘录”和“代表性原文句子”。
- 整体必须短，避免长句。

OCR Markdown 路径：{source_path}
OCR 元数据：{json.dumps(metadata, ensure_ascii=False, default=str)}

evidence:
{evidence}
""".strip()
    return _llm_json_call(prompt)


def _generate_ocr_conclusions_with_llm(*, evidence: str, source_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是离线端 OCR 文档总结器。这里只生成报告的“结论”和“风险复核”部分。

只输出一个 JSON object，不要 Markdown，不要代码块，不要解释。字段：
{{"conclusions":["每条不超过45字，2到3条"],"risks":["每条不超过35字，2条"]}}

规则：
- 不要编造 evidence 中没有的信息。
- 优先使用“结论/Conclusion摘录”。
- conclusions 只能总结 evidence 已出现的结论或明显主张。
- 不要把章节标题、目录、小节名当结论。
- 必须在 220 个中文字符内结束。

OCR Markdown 路径：{source_path}
OCR 元数据：{json.dumps(metadata, ensure_ascii=False, default=str)}

evidence:
{evidence}
""".strip()
    return _llm_json_call(prompt)


def _llm_json_call(prompt: str) -> dict[str, Any]:
    return _extract_json_object(llm_call(prompt))


def _fallback_summary(*, evidence: str, source_path: Path, error: str) -> dict[str, Any]:
    lines = _content_lines(evidence)
    title = _extract_labeled_value(lines, "文档标题") or source_path.stem
    abstract_lines = _extract_labeled_block(lines, "摘要/Abstract摘录")
    conclusion_lines = _extract_labeled_block(lines, "结论/Conclusion摘录")
    facts = [
        line.lstrip("-").strip()
        for line in lines
        if line.startswith("-") and _looks_like_content_line(line.lstrip("-").strip())
    ][:8]
    summary_source = abstract_lines or facts
    summary = _clip_text("；".join(summary_source[:3]), limit=220) or "LLM 未能完成 OCR 总结，当前报告基于 OCR evidence 生成抽取式短摘要。"
    fallback_conclusions = _rank_conclusion_lines(conclusion_lines + facts, limit=3) or [
        "当前结论来自 OCR 原文抽取，需结合原 PDF 复核。"
    ]
    return {
        "title": title,
        "summary": summary,
        "key_points": facts[:6] or ["OCR evidence 信息不足，需人工复核原文。"],
        "methods_or_workflow": [],
        "conclusions": fallback_conclusions,
        "risks": _fallback_risks(error),
        "mode": "extractive_fallback",
        "error": error,
    }


def _render_markdown(summary: dict[str, Any], *, source_path: Path, generated_at: str) -> str:
    lines = [
        f"# {summary['title']}",
        "",
        "## 摘要",
        summary["summary"],
        "",
        "## 关键事实",
        *_markdown_list(summary.get("key_points"), empty="暂无可确认关键事实。"),
        "",
    ]
    methods = _string_list(summary.get("methods_or_workflow"))
    if methods:
        lines.extend(
            [
                "## 方法与流程",
                *_markdown_list(methods, empty="暂无方法或流程信息。"),
                "",
            ]
        )
    lines.extend(
        [
            "## 结论",
            *_markdown_list(summary.get("conclusions"), empty="暂无明确结论。"),
            "",
            "## 风险与复核",
            *_markdown_list(summary.get("risks"), empty="暂无风险。"),
            "",
            "## 来源",
            f"- OCR Markdown：{source_path}",
            f"- 生成时间：{generated_at}",
            f"- 生成模式：{summary.get('mode')}",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_to_typst(markdown: str, *, title: str) -> str:
    lines = [
        f"#set document(title: [{_typst_escape(title)}])",
        "#set page(margin: 1.8cm)",
        '#set text(font: "Noto Sans CJK SC", size: 10.5pt)',
        "",
    ]
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            lines.append(f"= {_typst_escape(line[2:].strip())}")
        elif line.startswith("## "):
            lines.append(f"== {_typst_escape(line[3:].strip())}")
        elif line.startswith("- "):
            lines.append(f"- {_typst_escape(line[2:].strip())}")
        elif not line.strip():
            lines.append("")
        else:
            lines.append(_typst_escape(line))
    return "\n".join(lines) + "\n"


def _compile_typst(*, typ_path: Path, pdf_path: Path) -> dict[str, Any]:
    typst_bin = os.environ.get("TYPST_BIN") or shutil.which("typst")
    runtime_typst = WORKSPACE_DIR.parent / ".runtime" / "bin" / ("typst.exe" if os.name == "nt" else "typst")
    if not typst_bin and runtime_typst.exists():
        typst_bin = str(runtime_typst)
    if not typst_bin:
        return {"ok": False, "compiled": False, "error": "typst command not found; Markdown and Typst files were generated."}
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
    except Exception as exc:  # noqa: BLE001
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
        if _is_generic_ocr_line(line):
            continue
        lines.append(line)
    return lines


def _section_excerpt(markdown: str, *, headings: tuple[str, ...], limit: int) -> list[str]:
    result: list[str] = []
    capture = False
    for raw in markdown.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        heading_text = line.lstrip("#").strip()
        is_heading = _is_heading_line(line)
        if is_heading and any(key.lower() in heading_text.lower() for key in headings):
            capture = True
            continue
        if capture and is_heading:
            break
        if not capture:
            continue
        cleaned = _strip_bullet(line)
        if _looks_like_content_line(cleaned):
            result.append(cleaned[:220])
            if len(result) >= limit:
                break
    return result


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    if len(stripped) > 96:
        return False
    return bool(re.match(r"^\d+(?:\.\d+)*[\.\s]+[A-Z][A-Za-z /&:-]{2,}$", stripped))


def _first_long_paragraphs(markdown: str, *, limit: int) -> list[str]:
    result: list[str] = []
    for raw in markdown.replace("\r\n", "\n").splitlines():
        line = _strip_bullet(raw.strip())
        if _looks_like_content_line(line) and len(line) >= 80:
            result.append(line[:260])
            if len(result) >= limit:
                break
    return result


def _extract_labeled_value(lines: list[str], label: str) -> str:
    prefix = f"{label}："
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _extract_labeled_block(lines: list[str], label: str) -> list[str]:
    result: list[str] = []
    capture = False
    for line in lines:
        if line.rstrip("：") == label:
            capture = True
            continue
        if capture and line.endswith("：") and not line.startswith("-"):
            break
        if capture and line.startswith("-"):
            item = line.lstrip("-").strip()
            if _looks_like_content_line(item):
                result.append(item)
    return result


def _looks_like_content_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(line or "").strip())
    if _is_generic_ocr_line(normalized):
        return False
    if len(normalized) < 12:
        return False
    heading_only = {
        "abstract",
        "introduction",
        "related work",
        "method",
        "methods",
        "experiments",
        "experiment",
        "conclusion",
        "conclusions",
        "references",
        "摘要",
        "简介",
        "引言",
        "相关工作",
        "方法",
        "实验",
        "结论",
        "参考文献",
    }
    if normalized.strip("# ：:0123456789.、").lower() in heading_only:
        return False
    lowered = normalized.lower()
    if lowered.startswith(("figure ", "fig. ", "table ", "tab. ", "references", "acknowledg")):
        return False
    if re.match(r"^\d?\s*(college|school|department|institute|university)\b", lowered):
        return False
    if lowered.count("university") >= 2 or lowered.count("college") >= 2:
        return False
    return True


def _fallback_risks(error: str) -> list[str]:
    risks = ["OCR 可能存在错字、漏字、版面顺序错误、公式或表格识别不完整。"]
    if error:
        risks.insert(0, f"LLM 分段总结失败或截断：{error[:220]}")
    else:
        risks.insert(0, "LLM 分段总结未提供该部分，已使用 OCR 原文抽取结果。")
    return risks


def _clip_text(text: str, *, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[:limit]
    for mark in ("。", "；", ";", ".", "，", ","):
        index = clipped.rfind(mark)
        if index >= max(40, limit // 2):
            return clipped[: index + 1].strip()
    return clipped.strip()


def _rank_conclusion_lines(lines: list[str], *, limit: int) -> list[str]:
    scored: list[tuple[int, int, str]] = []
    bad = re.compile(r"^(effect of|figure|fig\.|table|tab\.|图\d|表\d|references)", re.IGNORECASE)
    good = re.compile(
        r"in this work|we propose|we introduce|we design|demonstrate|achieve|state-of-the-art|framework|results|conclude|本文|提出|实现|结果|性能|证明|表明"
    )
    seen: set[str] = set()
    for index, line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", str(line or "").strip())
        if not _looks_like_content_line(normalized) or normalized in seen or bad.search(normalized):
            continue
        seen.add(normalized)
        score = min(len(normalized), 180)
        if good.search(normalized):
            score += 120
        scored.append((score, -index, normalized[:220]))
    scored.sort(reverse=True)
    return [item[2] for item in scored[:limit]]


def _rank_representative_lines(lines: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    scored: list[tuple[int, int, str]] = []
    keywords = re.compile(r"\d|模型|系统|方法|实验|结果|安全|隐私|边缘|部署|流程|模块|数据|结论|OCR|BPU|数据|问题|目标|性能|对比|应用|风险|framework|module|experiment|result|tracking", re.IGNORECASE)
    for index, line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", line).strip()
        if not _looks_like_content_line(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        score = min(len(normalized), 180)
        if keywords.search(normalized):
            score += 80
        scored.append((score, -index, normalized[:220]))
    scored.sort(reverse=True)
    return [item[2] for item in scored[:limit]]


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\s*(?:[-*]|\d+[\.\)])\s*", "", line).strip()


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not _is_generic_ocr_line(stripped.lstrip("#").strip()):
            return stripped.lstrip("#").strip()
    for line in markdown.splitlines():
        stripped = line.strip().lstrip("#").lstrip("-").strip()
        if stripped and not stripped.endswith("：") and not _is_generic_ocr_line(stripped):
            return stripped[:80]
    return ""


def _is_generic_ocr_line(line: str) -> bool:
    normalized = re.sub(r"\s+", "", str(line or "").strip())
    if not normalized:
        return True
    if normalized in {"文档内容", "文档标题", "章节线索", "原文项目符号", "代表性原文句子"}:
        return True
    if normalized.startswith(("文档标题：文档内容", "文档标题:文档内容")):
        return True
    return bool(re.fullmatch(r"(第)?\d{1,4}页|page\d{1,4}", normalized, flags=re.IGNORECASE))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("title") or item.get("content")
            else:
                text = item
            normalized = str(text or "").strip()
            if normalized:
                result.append(normalized)
        return result
    return [str(value).strip()] if str(value).strip() else []


def _markdown_list(items: Any, *, empty: str) -> list[str]:
    values = _string_list(items)
    return [f"- {item}" for item in values] if values else [f"- {empty}"]


def _typst_escape(value: Any) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("#", "\\#")
        .replace("$", "\\$")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


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


def _preview(markdown: str) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"^#+\s*", "", markdown, flags=re.MULTILINE)).strip()
    return text[:500]


def _workspace_rel(path: Path | str) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(WORKSPACE_DIR.resolve()).as_posix()
    except ValueError:
        return str(candidate)
