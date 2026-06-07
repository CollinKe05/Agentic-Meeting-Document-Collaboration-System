"""RDK X5 各环节耗时测试 — 规则排序版"""
import sys
import time
from pathlib import Path

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from syss.config import SystemConfig
from syss.utils.pdf_utils import pdf_to_images
from syss.utils.json_utils import save_json


def benchmark():
    cfg = SystemConfig()
    _here = Path(__file__).resolve().parent  # syss/
    pdf = _here / "demo-6.pdf"
    if not pdf.exists():
        pdf = _PARENT / "office-AI-main" / "office-AI-main" / "sample" / "demo-6.pdf"
    out = _here / "output"

    print("=" * 50)
    print("RDK X5 各环节耗时测试")
    print(f"PDF: {pdf}")
    print(f"YOLO: {cfg.yolo_model}")
    print(f"OCR: {'BPU' if _detect_bpu() else 'ONNX (CPU)'}")
    print(f"排序: 坐标规则 (FastReadingOrderSorter)")
    print("=" * 50)

    timings = {}
    t_total = time.time()

    # ── 步骤1: PDF → 图片 ──
    t0 = time.time()
    images = pdf_to_images(str(pdf), dpi=cfg.dpi)
    timings["1_pdf_to_images"] = round(time.time() - t0, 2)
    print(f"[1] PDF → {len(images)}张图片  {timings['1_pdf_to_images']:.1f}s")

    # ── 步骤2: 版面分析 ──
    from syss.layout.analyzer import LayoutAnalyzer
    t0 = time.time()
    analyzer = LayoutAnalyzer(cfg.yolo_model, cfg.layout_conf, cfg.layout_iou, cfg.labels)
    blocks_by_page = analyzer.analyze_images(images)
    n_blocks = sum(len(b) for b in blocks_by_page)
    timings["2_layout"] = round(time.time() - t0, 2)
    print(f"[2] 版面分析 {n_blocks}个块  {timings['2_layout']:.1f}s")

    # ── 步骤3: OCR ──
    from syss.ocr.factory import create_ocr
    t0 = time.time()
    ocr = create_ocr(cfg)
    t_ocr_init = time.time() - t0
    t0 = time.time()
    ocr_results = ocr.process_images(images)
    n_texts = sum(len(r.results) for r in ocr_results)
    timings["3_ocr"] = round(time.time() - t0, 2)
    print(f"[3] OCR ({n_texts}条文本)  init={t_ocr_init:.1f}s  inference={timings['3_ocr']:.1f}s")

    # ── 步骤4: 合并 ──
    from syss.merge.merger import BlockOCRMerger
    t0 = time.time()
    merger = BlockOCRMerger(score_filter=cfg.block_score_filter)
    merged = merger.merge_all(blocks_by_page, ocr_results)
    save_json(merged, str(out / "demo-6_merged.json"))
    timings["4_merge"] = round(time.time() - t0, 2)
    print(f"[4] 合并  {timings['4_merge']:.1f}s")

    # ── 步骤5: 阅读排序 (规则) ──
    from syss.reading_order.fast_sorter import FastReadingOrderSorter
    sorter = FastReadingOrderSorter()
    t0 = time.time()
    sorted_data = sorter.sort(merged)
    save_json(sorted_data, str(out / "demo-6_sorted.json"))
    timings["5_reading_order"] = round(time.time() - t0, 2)
    print(f"[5] 阅读排序 (规则)  {timings['5_reading_order']:.1f}s")

    # ── 步骤6: 排序可视化 ──
    from syss.utils.visualize import visualize
    t0 = time.time()
    viz_dir = out / "reading_order_viz"
    visualize(str(out / "demo-6_sorted.json"), str(pdf), str(viz_dir), dpi=cfg.dpi)
    timings["6_viz"] = round(time.time() - t0, 2)
    print(f"[6] 排序图  {timings['6_viz']:.1f}s")

    # ── 步骤7: Markdown ──
    from syss.markdown.generator import json_to_markdown
    t0 = time.time()
    json_to_markdown(sorted_data, str(out / "demo-6.md"))
    timings["7_markdown"] = round(time.time() - t0, 2)
    print(f"[7] Markdown  {timings['7_markdown']:.1f}s")

    # ── 总结 ──
    timings["total"] = round(time.time() - t_total, 2)
    print("=" * 50)
    print(f"总耗时: {timings['total']:.1f}s")
    print(f"排序图: {viz_dir}")
    print()
    print("环节         耗时    占比")
    print("-" * 30)
    for name, sec in timings.items():
        if name == "total":
            continue
        pct = sec / timings["total"] * 100
        label = name.split("_", 1)[1]
        print(f"{label:<12} {sec:>5.1f}s  {pct:>5.0f}%")


def _detect_bpu():
    try:
        import hbm_runtime  # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False


if __name__ == "__main__":
    benchmark()
