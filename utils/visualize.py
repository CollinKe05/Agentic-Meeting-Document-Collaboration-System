"""阅读顺序可视化 — 在页面图片上标注文本框编号"""
import json
from pathlib import Path
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# 不同块类型的颜色
COLORS = {
    "title": "#e74c3c",
    "plain text": "#2ecc71",
    "abandon": "#95a5a6",
    "figure": "#3498db",
    "figure_caption": "#1abc9c",
    "table": "#9b59b6",
    "table_caption": "#e67e22",
    "table_footnote": "#f39c12",
    "isolate_formula": "#e91e63",
    "formula_caption": "#00bcd4",
    "标题": "#e74c3c",
    "正文": "#2ecc71",
    "废弃": "#95a5a6",
    "图片": "#3498db",
    "图片标题": "#1abc9c",
    "表格": "#9b59b6",
    "表格标题": "#e67e22",
    "表格脚注": "#f39c12",
    "公式": "#e91e63",
    "公式标题": "#00bcd4",
}


def find_font():
    for path in [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        if Path(path).exists():
            return path
    return None


def visualize(json_path: str, pdf_path: str, output_dir: str, dpi: int = 200):
    font_path = find_font()
    font_label = ImageFont.truetype(font_path, 14) if font_path else ImageFont.load_default()
    font_num = ImageFont.truetype(font_path, 12) if font_path else ImageFont.load_default()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc = fitz.open(pdf_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for page_data in data["pages"]:
        page_idx = page_data["page_index"]
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # 按 page_reading_order 收集所有文本框
        all_boxes = []
        for block in page_data["blocks"]:
            cls = block["block_info"]["class_name"]
            for tb in block["contained_text_boxes"]:
                ro = tb.get("page_reading_order", -1)
                if ro >= 0:
                    all_boxes.append((ro, tb["bbox"], cls, tb.get("is_virtual", False)))

        if not all_boxes:
            continue

        draw = ImageDraw.Draw(img)
        color_default = "#888888"

        for ro, bbox, cls, is_virtual in all_boxes:
            color = COLORS.get(cls, color_default)
            # bbox 已经是 pipeline 200 DPI 像素坐标，无需缩放
            x1, y1, x2, y2 = [int(v) for v in bbox]

            # 虚线表示虚拟文本框
            if is_virtual:
                for i in range(0, int(x2 - x1) - 5, 8):
                    draw.line([(x1 + i, y1), (x1 + min(i + 4, x2 - x1), y1)], fill="#ff9800", width=1)
                    draw.line([(x1 + i, y2), (x1 + min(i + 4, x2 - x1), y2)], fill="#ff9800", width=1)
                for i in range(0, int(y2 - y1) - 5, 8):
                    draw.line([(x1, y1 + i), (x1, y1 + min(i + 4, y2 - y1))], fill="#ff9800", width=1)
                    draw.line([(x2, y1 + i), (x2, y1 + min(i + 4, y2 - y1))], fill="#ff9800", width=1)
            else:
                draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # 在左上角标注编号
            label = str(ro)
            bbox_label = draw.textbbox((0, 0), label, font=font_num)
            tw, th = bbox_label[2] - bbox_label[0], bbox_label[3] - bbox_label[1]
            label_x, label_y = x1, max(0, y1 - th - 2)
            # 背景
            draw.rectangle([label_x, label_y, label_x + tw + 4, label_y + th + 2], fill=color)
            draw.text((label_x + 2, label_y + 1), label, fill="#ffffff", font=font_num)

        # 图例
        legend_x, legend_y = 10, 10
        for cls, color in [("标题", "#e74c3c"), ("正文", "#2ecc71"), ("图片", "#3498db"), ("表格", "#9b59b6"), ("公式", "#e91e63")]:
            draw.rectangle([legend_x, legend_y, legend_x + 12, legend_y + 12], fill=color)
            draw.text((legend_x + 16, legend_y - 1), cls, fill=color, font=font_label)
            legend_y += 18

        # 虚拟文本框说明
        draw.rectangle([legend_x, legend_y, legend_x + 12, legend_y + 12], outline="#ff9800", width=1)
        draw.text((legend_x + 16, legend_y - 1), "虚拟行(图表等)", fill="#ff9800", font=font_label)

        out_path = out / f"page_{page_idx + 1}.png"
        img.save(str(out_path))
        print(f"Page {page_idx + 1}: {len(all_boxes)} textboxes -> {out_path}")

    doc.close()


if __name__ == "__main__":
    import sys
    base = Path(__file__).resolve().parent.parent  # syss/
    json_path = base / "output" / "demo-6_sorted.json"
    pdf_path = base / "demo-6.pdf"
    if not pdf_path.exists():
        pdf_path = base.parent / "office-AI-main" / "office-AI-main" / "sample" / "demo-6.pdf"
    out_dir = base / "output" / "reading_order_viz"
    visualize(str(json_path), str(pdf_path), str(out_dir))
