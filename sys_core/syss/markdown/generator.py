from __future__ import annotations

from pathlib import Path
from typing import Any


def _extract_text(textbox: dict[str, Any]) -> str:
    if textbox.get("is_virtual", False):
        return ""
    return str(textbox.get("transcription", "")).strip()


def _block_prefix(class_name: str, level: int = 1) -> str:
    cls = class_name.lower()
    if "title" in cls:
        return "#" * min(level + 1, 6) + " "
    if "figure_caption" in cls:
        return "*图注: "
    if "table_caption" in cls:
        return "*表注: "
    if cls in {"figure", "table", "isolate_formula"}:
        return f"**[{cls.upper()}]**\n\n"
    return ""


def _block_suffix(class_name: str) -> str:
    cls = class_name.lower()
    if "figure_caption" in cls or "table_caption" in cls:
        return "*"
    return ""


def json_to_markdown(data: dict[str, Any], output_path: str) -> None:
    lines = ["# 文档内容\n\n"]

    for page_data in data.get("pages", []):
        page_idx = int(page_data.get("page_index", 0))
        lines.append(f"## 第 {page_idx + 1} 页\n\n")

        for block in page_data.get("blocks", []):
            block_info = block.get("block_info", {})
            class_name = str(block_info.get("class_name", "unknown"))
            if class_name.lower() == "abandon":
                continue

            textboxes = block.get("contained_text_boxes", [])
            sorted_tbs = sorted(
                [tb for tb in textboxes if tb.get("page_reading_order", -1) >= 0],
                key=lambda item: item.get("page_reading_order", float("inf")),
            )
            texts = [text for text in (_extract_text(tb) for tb in sorted_tbs) if text]

            if texts:
                title_level = 2 if "title" in class_name.lower() else 3
                prefix = _block_prefix(class_name, title_level)
                suffix = _block_suffix(class_name)

                if class_name.lower() in {"figure", "table", "isolate_formula"}:
                    _append_media_block(lines, class_name, block_info, prefix)
                elif "title" in class_name.lower():
                    lines.append(f"{prefix}{' '.join(texts)}\n\n")
                else:
                    if prefix:
                        lines.append(prefix)
                    lines.append(f"{' '.join(texts)}{suffix}\n\n")
            elif class_name.lower() in {"figure", "table", "isolate_formula"}:
                _append_media_block(lines, class_name, block_info, _block_prefix(class_name))

        lines.append("\n---\n\n")

    Path(output_path).write_text("".join(lines), encoding="utf-8", newline="\n")


def json_to_markdown_detailed(data: dict[str, Any], output_path: str) -> None:
    lines = ["# 文档内容（详细结构）\n\n", "## 目录\n\n"]
    for page_data in data.get("pages", []):
        page_idx = int(page_data.get("page_index", 0))
        lines.append(f"- [第 {page_idx + 1} 页](#第-{page_idx + 1}-页)\n")
    lines.append("\n---\n\n")

    for page_data in data.get("pages", []):
        page_idx = int(page_data.get("page_index", 0))
        page_info = page_data.get("page_info", {})
        lines.append(f"## 第 {page_idx + 1} 页\n\n")
        lines.append(
            f"*块数: {page_info.get('total_blocks', '?')}, "
            f"文本框数: {page_info.get('total_textboxes', '?')}*\n\n"
        )

        for block in page_data.get("blocks", []):
            block_info = block.get("block_info", {})
            class_name = str(block_info.get("class_name", "unknown"))
            median_order = block_info.get("textbox_reading_order_median", -1)
            if class_name.lower() == "abandon":
                continue

            lines.append(f"### {class_name}\n\n")
            lines.append(f"*中位阅读顺序: {median_order}*\n\n")
            if class_name.lower() in {"figure", "table", "isolate_formula"}:
                _append_media_block(lines, class_name, block_info, f"**[{class_name.upper()}]** *(无图像)*\n\n")
            else:
                textboxes = block.get("contained_text_boxes", [])
                sorted_tbs = sorted(
                    [tb for tb in textboxes if tb.get("page_reading_order", -1) >= 0],
                    key=lambda item: item.get("page_reading_order", float("inf")),
                )
                texts = [text for text in (_extract_text(tb) for tb in sorted_tbs) if text]
                if texts:
                    text = " ".join(texts)
                    lines.append(f"**{text}**\n\n" if "title" in class_name.lower() else f"{text}\n\n")
                else:
                    lines.append("*(无文本内容)*\n\n")
            lines.append("---\n\n")

    Path(output_path).write_text("".join(lines), encoding="utf-8", newline="\n")


def _append_media_block(lines: list[str], class_name: str, block_info: dict[str, Any], fallback: str) -> None:
    crop = str(block_info.get("crop_image_path", "") or "")
    if crop:
        image_name = Path(crop).name
        lines.append(f"![{class_name.upper()}: {image_name}]({crop})\n\n")
    else:
        lines.append(fallback)
