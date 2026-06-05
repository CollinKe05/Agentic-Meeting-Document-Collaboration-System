"""文档处理流水线 — 串联 5 步"""
import gc
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import SystemConfig
from .utils.image_utils import imread_cn, imwrite_cn
from .utils.json_utils import save_json
from .merge.merger import BlockOCRMerger
from .markdown.generator import json_to_markdown

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class PageImage:
    page_idx: int
    path: Path
    width: int
    height: int


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
            if _layoutreader_has_weights(self.cfg.layoutreader_model):
                try:
                    from .reading_order.sorter import ReadingOrderSorter
                    self._sorter = ReadingOrderSorter(self.cfg.layoutreader_model)
                except Exception as exc:  # noqa: BLE001 - model availability varies on WSL/board
                    print(f"[排序] LayoutReader 不可用，回退快速排序: {exc}")
                    from .reading_order.fast_sorter import FastReadingOrderSorter
                    self._sorter = FastReadingOrderSorter()
            else:
                print("[排序] LayoutReader 权重缺失，使用快速坐标排序")
                from .reading_order.fast_sorter import FastReadingOrderSorter
                self._sorter = FastReadingOrderSorter()
        return self._sorter

    def run(self, input_path: str, output_dir: str) -> dict:
        """完整流水线, 返回 {merged_json, sorted_json, markdown, pages}"""
        t0 = time.time()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        source = Path(input_path)
        stem = source.stem

        print(f"[Pipeline] 开始处理: {input_path}")
        print(f"[Pipeline] 输出目录: {out}")

        checkpoint_dir = out / f"{stem}_checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 步骤1: 输入 → 页图文件
        t1 = time.time()
        pages, images_dir = _prepare_page_images(source, out, dpi=self.cfg.dpi)
        print(f"[步骤1] 输入→{len(pages)}张页图, {time.time() - t1:.1f}s")

        # BPU OCR 可以和 CPU YOLO 重叠；CPU OCR 回退时保持串行，避免抢核。
        ocr_future: Future[list] | None = None
        executor: ThreadPoolExecutor | None = None
        ocr_started_at: float | None = None
        ocr_overlap = _should_overlap_ocr(self.cfg)
        if ocr_overlap:
            ocr_started_at = time.time()
            executor = ThreadPoolExecutor(max_workers=1)
            ocr_future = executor.submit(self._process_ocr_pages, pages, checkpoint_dir)
            print("[步骤2] BPU OCR 后台预取已启动")

        # 步骤2: 版面分析，YOLO 模型加载一次，连续跑所有页。
        t2 = time.time()
        blocks_by_page = self._process_layout_pages(pages, checkpoint_dir)
        total_blocks = sum(len(b) for b in blocks_by_page)
        layout_backend = type(self.layout).__name__
        print(f"[步骤2] 版面分析: {total_blocks}个块, {time.time() - t2:.1f}s")

        # 步骤3: OCR 结果收口。BPU 已后台跑时通常只剩极短等待。
        if ocr_future is not None:
            assert ocr_started_at is not None
            wait_started = time.time()
            try:
                ocr_results = ocr_future.result()
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)
            print(
                f"[步骤3] OCR 后台完成, 总耗时 {time.time() - ocr_started_at:.1f}s, "
                f"主线程等待 {time.time() - wait_started:.1f}s"
            )
        else:
            t3 = time.time()
            ocr_results = self._process_ocr_pages(pages, checkpoint_dir)
            print(f"[步骤3] OCR 串行完成, {time.time() - t3:.1f}s")
        total_texts = sum(len(r.results) for r in ocr_results)
        print(f"[步骤3] OCR: {total_texts}条文本")

        # 步骤4: 合并 + 虚拟行，结构很小，内存流转并落盘 checkpoint。
        t4 = time.time()
        merged = self._merger.merge_all(blocks_by_page, ocr_results)
        _attach_page_sizes(merged, pages)
        _save_merged_page_checkpoints(merged, checkpoint_dir)
        merged_path = out / f"{stem}_merged.json"
        save_json(merged, str(merged_path))
        print(f"[步骤4] 合并完成, {time.time() - t4:.1f}s")

        if self.cfg.keep_temp:
            print(f"  -> {merged_path}")

        # 步骤5: 释放 YOLO 引用，再加载 LayoutReader/快速排序连续处理全部页。
        self._layout = None
        gc.collect()
        t5 = time.time()
        sorted_data = self.sorter.sort(merged)
        _save_sorted_page_checkpoints(sorted_data, checkpoint_dir)
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
            "images_dir": str(images_dir) if images_dir is not None else None,
            "checkpoint_dir": str(checkpoint_dir),
            "pages": len(pages),
            "block_count": total_blocks,
            "text_count": total_texts,
            "ocr_backend": type(self.ocr).__name__,
            "ocr_overlap": ocr_overlap,
            "sorter_backend": type(self.sorter).__name__,
            "layout_backend": layout_backend,
            "elapsed": round(total, 1),
        }

    def _process_layout_pages(self, pages: list[PageImage], checkpoint_dir: Path) -> list[list]:
        blocks_by_page = []
        for page in pages:
            image = imread_cn(str(page.path))
            blocks = self.layout.analyze(image, page.page_idx)
            blocks_by_page.append(blocks)
            save_json(
                _layout_blocks_to_dict(blocks, page.page_idx),
                str(checkpoint_dir / f"layout_page_{page.page_idx + 1:03d}.json"),
            )
            del image
        return blocks_by_page

    def _process_ocr_pages(self, pages: list[PageImage], checkpoint_dir: Path) -> list:
        results = []
        for page in pages:
            image = imread_cn(str(page.path))
            result = self.ocr.process_image(image, page.page_idx)
            results.append(result)
            save_json(_ocr_result_to_dict(result), str(checkpoint_dir / f"ocr_page_{page.page_idx + 1:03d}.json"))
            del image
        return results


def _prepare_page_images(input_path: Path, output_dir: Path, *, dpi: int) -> tuple[list[PageImage], Path | None]:
    suffix = input_path.suffix.lower()
    if suffix == ".pdf":
        return _render_pdf_to_page_images(input_path, output_dir, dpi=dpi)
    if suffix in IMAGE_SUFFIXES:
        image = imread_cn(str(input_path))
        if image is None:
            raise ValueError(f"Cannot read image: {input_path}")
        height, width = image.shape[:2]
        del image
        return [PageImage(page_idx=0, path=input_path, width=int(width), height=int(height))], None
    raise ValueError(f"Unsupported SYSS document type: {input_path.suffix}")


def _render_pdf_to_page_images(input_path: Path, output_dir: Path, *, dpi: int) -> tuple[list[PageImage], Path]:
    import cv2
    import fitz

    page_dir = output_dir / f"{input_path.stem}_pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    pages: list[PageImage] = []
    doc = fitz.open(str(input_path))
    try:
        for index in range(len(doc)):
            page = doc.load_page(index)
            pix = page.get_pixmap(dpi=dpi)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
            if pix.n == 4:
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            elif pix.n == 1:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            path = page_dir / f"page_{index + 1:03d}.png"
            imwrite_cn(str(path), image)
            pages.append(PageImage(page_idx=index, path=path, width=int(pix.width), height=int(pix.height)))
            del image, pix
    finally:
        doc.close()
    return pages, page_dir


def _attach_page_sizes(merged: dict, pages: list[PageImage]) -> None:
    for page_image in pages:
        page = merged.get(f"page{page_image.page_idx}")
        if not page:
            continue
        page.setdefault("page_info", {})
        page["page_info"].update({"page_width": page_image.width, "page_height": page_image.height})


def _layout_blocks_to_dict(blocks: list, page_idx: int) -> dict:
    return {
        "page_index": page_idx,
        "blocks": [
            {
                "class_name": block.class_name,
                "bbox": block.bbox,
                "score": block.score,
                "page_idx": block.page_idx,
                "block_idx": block.block_idx,
            }
            for block in blocks
        ],
    }


def _ocr_result_to_dict(result) -> dict:
    return {
        "page_index": result.page_idx,
        "results": [
            {
                "bbox": item.bbox,
                "transcription": item.transcription,
                "score": item.score,
                "illegibility": item.illegibility,
            }
            for item in result.results
        ],
    }


def _save_merged_page_checkpoints(merged: dict, checkpoint_dir: Path) -> None:
    for key, page in sorted(merged.items(), key=lambda item: item[1].get("page_info", {}).get("page_index", 0)):
        page_idx = int(page.get("page_info", {}).get("page_index", key.replace("page", "") or 0))
        save_json(page, str(checkpoint_dir / f"merged_page_{page_idx + 1:03d}.json"))


def _save_sorted_page_checkpoints(sorted_data: dict, checkpoint_dir: Path) -> None:
    for page in sorted_data.get("pages", []):
        page_idx = int(page.get("page_index", 0))
        save_json(page, str(checkpoint_dir / f"sorted_page_{page_idx + 1:03d}.json"))


def _should_overlap_ocr(config: SystemConfig) -> bool:
    value = os.environ.get("SYSS_BPU_OVERLAP")
    if value is not None and value.strip().lower() in {"0", "false", "no", "off"}:
        return False
    if not (_path_exists(config.bpu_runtime_dir) and _path_exists(config.bpu_det_model) and _path_exists(config.bpu_rec_model)):
        return False
    try:
        import hbm_runtime  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        return False
    return True


def _path_exists(path: str) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def _layoutreader_has_weights(model_path: str) -> bool:
    if not model_path:
        return False
    path = Path(model_path)
    if not path.exists():
        return False
    if path.is_file():
        return True
    weight_names = {"pytorch_model.bin", "model.safetensors", "tf_model.h5"}
    return any((path / name).exists() for name in weight_names)
