"""将阅读排序后的 JSON 转换为 Markdown"""
import re
from pathlib import Path


def _extract_text(textbox):
    if textbox.get("is_virtual", False):
        return ""
    return textbox.get("transcription", "").strip()


def _block_prefix(class_name, level=1):
    cls = class_name.lower()
    if "title" in cls:
        return "#" * min(level + 1, 6) + " "
    if "figure_caption" in cls:
        return "*图注: "
    if "table_caption" in cls:
        return "*表注: "
    if cls in ("figure", "table", "isolate_formula"):
        return f"**[{cls.upper()}]**\n\n"
    return ""


def _block_suffix(class_name):
    cls = class_name.lower()
    if "figure_caption" in cls or "table_caption" in cls:
        return "*"
    return ""


def json_to_markdown(data: dict, output_path: str):
    """将 sorted JSON 转为简洁 Markdown"""
    lines = ["# 文档内容\n"]

    for page_data in data["pages"]:
        page_idx = page_data["page_index"]
        lines.append(f"## 第 {page_idx + 1} 页\n")

        for block in page_data["blocks"]:
            block_info = block.get("block_info", {})
            class_name = block_info.get("class_name", "unknown")
            if class_name.lower() == "abandon":
                continue

            textboxes = block.get("contained_text_boxes", [])
            sorted_tbs = sorted(
                [tb for tb in textboxes if tb.get("page_reading_order", -1) >= 0],
                key=lambda x: x.get("page_reading_order", float("inf"))
            )

            texts = [_extract_text(tb) for tb in sorted_tbs]
            texts = [t for t in texts if t]

            if texts:
                title_level = 2 if "title" in class_name.lower() else 3
                prefix = _block_prefix(class_name, title_level)
                suffix = _block_suffix(class_name)

                if class_name.lower() in ("figure", "table", "isolate_formula"):
                    crop = block_info.get("crop_image_path", "")
                    if crop:
                        image_name = Path(crop).name
                        lines.append(f"![{class_name.upper()}: {image_name}]({crop})\n\n")
                    else:
                        lines.append(f"{prefix}\n")
                elif "title" in class_name.lower():
                    lines.append(f"{prefix}{' '.join(texts)}\n")
                else:
                    if prefix:
                        lines.append(prefix)
                    lines.append(f"{' '.join(texts)}{suffix}\n")
                lines.append("\n")
            elif class_name.lower() in ("figure", "table", "isolate_formula"):
                prefix = _block_prefix(class_name)
                crop = block_info.get("crop_image_path", "")
                if crop:
                    image_name = Path(crop).name
                    lines.append(f"![{class_name.upper()}: {image_name}]({crop})\n\n")
                else:
                    lines.append(f"{prefix}\n")

        lines.append("\n---\n\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def json_to_markdown_detailed(data: dict, output_path: str):
    """将 sorted JSON 转为带结构信息的详细 Markdown"""
    lines = ["# 文档内容（详细结构）\n\n## 目录\n\n"]
    for page_data in data["pages"]:
        pi = page_data["page_index"]
        lines.append(f"- [第 {pi + 1} 页](#第-{pi + 1}-页)\n")
    lines.append("\n---\n\n")

    for page_data in data["pages"]:
        pi = page_data["page_index"]
        page_info = page_data["page_info"]
        lines.append(f"## 第 {pi + 1} 页\n")
        lines.append(
            f"*块数: {page_info.get('total_blocks', '?')}, "
            f"文本框数: {page_info.get('total_textboxes', '?')}*\n\n"
        )

        for block in page_data["blocks"]:
            block_info = block.get("block_info", {})
            class_name = block_info.get("class_name", "unknown")
            median_order = block_info.get("textbox_reading_order_median", -1)
            if class_name.lower() == "abandon":
                continue

            lines.append(f"### {class_name}\n")
            lines.append(f"*中位数阅读顺序: {median_order}*\n\n")

            if class_name.lower() in ("figure", "table", "isolate_formula"):
                crop = block_info.get("crop_image_path", "")
                if crop:
                    image_name = Path(crop).name
                    lines.append(f"![{class_name.upper()}: {image_name}]({crop})\n\n")
                else:
                    lines.append(f"**[{class_name.upper()}]** *(无图像)*\n\n")
            else:
                textboxes = block.get("contained_text_boxes", [])
                sorted_tbs = sorted(
                    [tb for tb in textboxes if tb.get("page_reading_order", -1) >= 0],
                    key=lambda x: x.get("page_reading_order", float("inf"))
                )
                texts = [_extract_text(tb) for tb in sorted_tbs]
                texts = [t for t in texts if t]
                if texts:
                    if "title" in class_name.lower():
                        lines.append(f"**{' '.join(texts)}**\n\n")
                    else:
                        lines.append(f"{' '.join(texts)}\n\n")
                else:
                    lines.append("*（无文本内容）*\n\n")
            lines.append("---\n\n")
        lines.append("\n\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
