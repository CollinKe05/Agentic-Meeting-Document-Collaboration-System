"""版面块 + OCR 结果合并 (含虚拟文本框生成)"""
from typing import List, Dict
from dataclasses import dataclass, field

from ..layout.analyzer import LayoutBlock
from ..ocr.base import PageOCRResult, OCRResult

SPECIAL_TYPES = {"figure", "table", "isolate_formula", "图片", "表格", "公式"}


@dataclass
class TextBox:
    bbox: list
    transcription: str
    score: float
    is_virtual: bool = False
    illegibility: bool = False


@dataclass
class MergedBlock:
    class_name: str
    bbox: list
    score: float
    block_idx: int
    page_idx: int
    is_virtual_text: bool = False
    text_boxes: List[TextBox] = field(default_factory=list)


class BlockOCRMerger:
    def __init__(self, score_filter: float = 0.5):
        self.score_filter = score_filter

    def merge_page(self, blocks: List[LayoutBlock],
                   ocr_result: PageOCRResult) -> List[MergedBlock]:
        valid_blocks = [b for b in blocks
                        if b.score >= self.score_filter and b.class_name.lower() != "abandon"]

        text_boxes = ocr_result.results
        avg_height = self._avg_text_height(text_boxes, valid_blocks)

        # 检测是否多栏：找页面中间间隙
        page_w, page_x_min = self._page_extent(valid_blocks, text_boxes)
        page_center_x = page_x_min + page_w / 2
        is_multi_col = self._detect_multi_col(text_boxes, page_w)

        assigned = [False] * len(text_boxes)

        merged = []
        for block in valid_blocks:
            is_special = block.class_name.lower() in SPECIAL_TYPES
            mb = MergedBlock(
                class_name=block.class_name, bbox=list(block.bbox),
                score=block.score, block_idx=block.block_idx,
                page_idx=block.page_idx, is_virtual_text=is_special)

            real_boxes = []
            for i, tb in enumerate(text_boxes):
                if assigned[i]:
                    continue
                # 多栏页面跳过通栏宽框 (OCR检测错误, 左右栏混在一起)
                # 只有宽且x中心靠近页面中心的框才过滤 (正常宽框即使稍宽也保留)
                if is_multi_col:
                    box_w = tb.bbox[2] - tb.bbox[0]
                    if box_w > page_w * 0.45:
                        box_xc = (tb.bbox[0] + tb.bbox[2]) / 2
                        center_dist = abs(box_xc - page_center_x) / page_w
                        if center_dist < 0.12:
                            continue
                if self._overlaps(tb.bbox, block.bbox):
                    assigned[i] = True
                    real_boxes.append(TextBox(
                        bbox=list(tb.bbox), transcription=tb.transcription,
                        score=tb.score, is_virtual=False,
                        illegibility=tb.illegibility))

            if is_special:
                # 真实文本框 + 虚拟文本框混合，按 y 排序
                virtual = self._virtual_text_boxes(block.bbox, avg_height)
                mb.text_boxes = sorted(real_boxes + virtual, key=lambda t: t.bbox[1])
            else:
                mb.text_boxes = real_boxes

            merged.append(mb)
        return merged

    def merge_all(self, blocks_by_page: List[List[LayoutBlock]],
                  ocr_results: List[PageOCRResult]) -> Dict:
        result = {}
        for blocks, ocr in zip(blocks_by_page, ocr_results):
            merged = self.merge_page(blocks, ocr)
            page_key = f"page{ocr.page_idx}"
            result[page_key] = {
                "page_info": {
                    "page_index": ocr.page_idx,
                    "total_blocks": len(blocks),
                    "valid_blocks": len(merged),
                    "total_text_boxes": sum(len(m.text_boxes) for m in merged),
                },
                "blocks": [self._to_dict(m) for m in merged]
            }
        return result

    def _to_dict(self, mb: MergedBlock) -> dict:
        return {
            "block_info": {
                "class_name": mb.class_name, "bbox": mb.bbox,
                "score": mb.score, "block_idx": mb.block_idx,
                "page_idx": mb.page_idx, "is_virtual_text": mb.is_virtual_text,
            },
            "contained_text_boxes": [
                {
                    "bbox": t.bbox, "transcription": t.transcription,
                    "score": t.score, "is_virtual": t.is_virtual,
                    "illegibility": t.illegibility,
                } for t in mb.text_boxes
            ]
        }

    @staticmethod
    def _center_in(tb_bbox, block_bbox):
        cx = (tb_bbox[0] + tb_bbox[2]) / 2
        cy = (tb_bbox[1] + tb_bbox[3]) / 2
        return (block_bbox[0] <= cx <= block_bbox[2] and
                block_bbox[1] <= cy <= block_bbox[3])

    @staticmethod
    def _overlaps(tb_bbox, block_bbox):
        """文本框与块是否有显著重叠 (交集面积 > 文本框面积10%)"""
        x1 = max(tb_bbox[0], block_bbox[0])
        y1 = max(tb_bbox[1], block_bbox[1])
        x2 = min(tb_bbox[2], block_bbox[2])
        y2 = min(tb_bbox[3], block_bbox[3])
        if x1 >= x2 or y1 >= y2:
            return False
        inter = (x2 - x1) * (y2 - y1)
        tb_area = (tb_bbox[2] - tb_bbox[0]) * (tb_bbox[3] - tb_bbox[1])
        return tb_area > 0 and inter / tb_area > 0.1

    @staticmethod
    def _page_extent(blocks, text_boxes):
        xs = []
        for b in blocks:
            xs.extend([b.bbox[0], b.bbox[2]])
        for tb in text_boxes:
            xs.extend([tb.bbox[0], tb.bbox[2]])
        return (max(xs) - min(xs), min(xs)) if xs else (1, 0)

    @staticmethod
    def _detect_multi_col(text_boxes, page_w):
        """检测页面是否多栏: 找中间区域x中心最大间隙"""
        if len(text_boxes) < 4:
            return False
        x_centers = sorted((tb.bbox[0] + tb.bbox[2]) / 2 for tb in text_boxes)
        best_gap = 0
        best_mid = 0
        all_x = [tb.bbox[0] for tb in text_boxes] + [tb.bbox[2] for tb in text_boxes]
        page_min = min(all_x)
        for i in range(1, len(x_centers)):
            mid = (x_centers[i] + x_centers[i - 1]) / 2
            rel = (mid - page_min) / page_w if page_w > 0 else 0
            if rel < 0.2 or rel > 0.8:
                continue
            gap = x_centers[i] - x_centers[i - 1]
            if gap > best_gap:
                best_gap = gap
                best_mid = mid
        return best_gap > page_w * 0.12

    @staticmethod
    def _avg_text_height(text_boxes, blocks):
        excluded = []
        for b in blocks:
            if b.class_name.lower() in SPECIAL_TYPES:
                excluded.append(b.bbox)
        heights = []
        for tb in text_boxes:
            in_excluded = any(
                BlockOCRMerger._center_in(tb.bbox, eb) for eb in excluded)
            if not in_excluded:
                h = tb.bbox[3] - tb.bbox[1]
                if h > 0: heights.append(h)
        return sum(heights) / len(heights) if heights else 20.0

    @staticmethod
    def _virtual_text_boxes(bbox, avg_h, spacing=1.2):
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0: return []
        line_h = avg_h * spacing
        n = max(1, int(bh / line_h))
        boxes = []
        for i in range(n):
            y0 = y1 + i * line_h
            y3 = min(y0 + avg_h, y2)
            if y0 >= y2: break
            boxes.append(TextBox(
                bbox=[x1, y0, x2, y3], transcription="",
                score=1.0, is_virtual=True))
        return boxes
