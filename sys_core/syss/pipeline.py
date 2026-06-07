from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from .config import SystemConfig
from .markdown.generator import json_to_markdown
from .merge.merger import BlockOCRMerger
from .utils.json_utils import save_json
from .utils.pdf_utils import pdf_to_images


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class DocumentPipeline:
    def __init__(self, config: SystemConfig | None = None) -> None:
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
                self.cfg.yolo_model,
                self.cfg.layout_conf,
                self.cfg.layout_iou,
                self.cfg.labels,
            )
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
            from .reading_order.fast_sorter import FastReadingOrderSorter

            self._sorter = FastReadingOrderSorter()
        return self._sorter

    def run(self, input_path: str, output_dir: str) -> dict[str, Any]:
        t0 = time.time()
        source = Path(input_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = source.stem

        print(f"[Pipeline] start: {source}")
        print(f"[Pipeline] output: {out}")

        t1 = time.time()
        images = self._load_images(source)
        images_dir = out / f"{stem}_pages"
        if self.cfg.keep_temp:
            images_dir.mkdir(parents=True, exist_ok=True)
        print(f"[step 1] load images: {len(images)} page(s), {time.time() - t1:.1f}s")

        t2 = time.time()
        blocks_by_page = self.layout.analyze_images(images)
        total_blocks = sum(len(blocks) for blocks in blocks_by_page)
        print(f"[step 2] layout: {total_blocks} block(s), {time.time() - t2:.1f}s")

        t3 = time.time()
        ocr_results = self.ocr.process_images(images)
        total_texts = sum(len(result.results) for result in ocr_results)
        print(f"[step 3] ocr: {total_texts} text box(es), {time.time() - t3:.1f}s")

        t4 = time.time()
        merged = self._merger.merge_all(blocks_by_page, ocr_results)
        merged_path = out / f"{stem}_merged.json"
        save_json(merged, str(merged_path))
        print(f"[step 4] merge: {time.time() - t4:.1f}s")

        t5 = time.time()
        sorted_data = self.sorter.sort(merged)
        sorted_path = out / f"{stem}_sorted.json"
        save_json(sorted_data, str(sorted_path))
        print(f"[step 5] reading order: {time.time() - t5:.1f}s")

        t6 = time.time()
        markdown_path = out / f"{stem}.md"
        json_to_markdown(sorted_data, str(markdown_path))
        print(f"[step 6] markdown: {time.time() - t6:.1f}s")

        elapsed = round(time.time() - t0, 1)
        return {
            "merged_json": str(merged_path),
            "sorted_json": str(sorted_path),
            "markdown": str(markdown_path),
            "pages": len(images),
            "elapsed": elapsed,
            "block_count": total_blocks,
            "text_count": total_texts,
            "images_dir": str(images_dir) if images_dir.exists() else None,
            "layout_backend": Path(self.cfg.yolo_model).name if self.cfg.yolo_model else "",
            "ocr_backend": type(self.ocr).__name__,
            "sorter_backend": type(self.sorter).__name__,
        }

    def _load_images(self, source: Path) -> list[np.ndarray]:
        suffix = source.suffix.lower()
        if suffix == ".pdf":
            return pdf_to_images(str(source), dpi=self.cfg.dpi)
        if suffix in IMAGE_SUFFIXES:
            from .utils.image_utils import imread_cn

            image = imread_cn(str(source))
            if image is None:
                raise ValueError(f"Failed to read image: {source}")
            return [image]
        raise ValueError(f"Unsupported document type: {source.suffix}")
