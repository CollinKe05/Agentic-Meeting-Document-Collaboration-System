"""文档处理流水线 — 串联 5 步"""
import time
from pathlib import Path
from typing import List

import numpy as np

from .config import SystemConfig
from .utils.pdf_utils import pdf_to_images
from .utils.json_utils import save_json
from .merge.merger import BlockOCRMerger
from .markdown.generator import json_to_markdown


class DocumentPipeline:
    def __init__(self, config: SystemConfig = None):
        self.cfg = config or SystemConfig()
        self._layout = None
        self._ocr = None
        self._merger = BlockOCRMerger(score_filter=self.cfg.block_score_filter)
        self._sorter = None

    @property
    def layout(self):
        if self._layout is None:
            from .layout.analyzer import LayoutAnalyzer
            self._layout = LayoutAnalyzer(
                self.cfg.yolo_model, self.cfg.layout_conf,
                self.cfg.layout_iou, self.cfg.labels)
        return self._layout

    @property
    def ocr(self):
        if self._ocr is None:
            from .ocr.factory import create_ocr
            self._ocr = create_ocr(self.cfg)
        return self._ocr

    @property
    def sorter(self):
        if self._sorter is None:
            from .reading_order.sorter import ReadingOrderSorter
            self._sorter = ReadingOrderSorter(self.cfg.layoutreader_model)
        return self._sorter

    def run(self, pdf_path: str, output_dir: str) -> dict:
        """完整流水线, 返回 {merged_json, sorted_json, markdown, pages}"""
        t0 = time.time()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(pdf_path).stem

        print(f"[Pipeline] 开始处理: {pdf_path}")
        print(f"[Pipeline] 输出目录: {out}")

        # 步骤1: PDF → 图片
        t1 = time.time()
        images: List[np.ndarray] = pdf_to_images(pdf_path, dpi=self.cfg.dpi)
        print(f"[步骤1] PDF→{len(images)}张图片, {time.time() - t1:.1f}s")

        # 步骤2: 版面分析
        t2 = time.time()
        blocks_by_page: List[List[LayoutBlock]] = self.layout.analyze_images(images)
        total_blocks = sum(len(b) for b in blocks_by_page)
        print(f"[步骤2] 版面分析: {total_blocks}个块, {time.time() - t2:.1f}s")

        # 步骤3: OCR
        t3 = time.time()
        ocr_results: List[PageOCRResult] = self.ocr.process_images(images)
        total_texts = sum(len(r.results) for r in ocr_results)
        print(f"[步骤3] OCR: {total_texts}条文本, {time.time() - t3:.1f}s")

        # 步骤4: 合并
        t4 = time.time()
        merged = self._merger.merge_all(blocks_by_page, ocr_results)
        merged_path = out / f"{stem}_merged.json"
        save_json(merged, str(merged_path))
        print(f"[步骤4] 合并完成, {time.time() - t4:.1f}s")

        if self.cfg.keep_temp:
            print(f"  -> {merged_path}")

        # 步骤5: 阅读排序
        t5 = time.time()
        sorted_data = self.sorter.sort(merged)
        sorted_path = out / f"{stem}_sorted.json"
        save_json(sorted_data, str(sorted_path))
        print(f"[步骤5] 阅读排序完成, {time.time() - t5:.1f}s")

        if self.cfg.keep_temp:
            print(f"  -> {sorted_path}")

        # 步骤6: Markdown 生成
        t6 = time.time()
        md_path = out / f"{stem}.md"
        json_to_markdown(sorted_data, str(md_path))
        print(f"[步骤6] Markdown生成, {time.time() - t6:.1f}s")

        total = time.time() - t0
        print(f"[Pipeline] 完成, 总耗时 {total:.1f}s")
        print(f"  Markdown: {md_path}")

        return {
            "merged_json": str(merged_path),
            "sorted_json": str(sorted_path),
            "markdown": str(md_path),
            "pages": len(images),
            "elapsed": round(total, 1),
        }
