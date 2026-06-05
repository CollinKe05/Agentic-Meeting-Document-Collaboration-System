"""虚拟行阅读排序 — LayoutLMv3 (LayoutReader)"""
import statistics
from collections import defaultdict

import torch
import numpy as np
from transformers import LayoutLMv3ForTokenClassification

MAX_LEN = 510
CLS_ID, UNK_ID, EOS_ID = 0, 3, 2


def _boxes2inputs(boxes):
    bbox = [[0, 0, 0, 0]] + boxes + [[0, 0, 0, 0]]
    input_ids = [CLS_ID] + [UNK_ID] * len(boxes) + [EOS_ID]
    attention_mask = [1] + [1] * len(boxes) + [1]
    return {
        "bbox": torch.tensor([bbox]),
        "attention_mask": torch.tensor([attention_mask]),
        "input_ids": torch.tensor([input_ids]),
    }


def _prepare_inputs(inputs, model):
    ret = {}
    for k, v in inputs.items():
        v = v.to(model.device)
        if torch.is_floating_point(v):
            v = v.to(model.dtype)
        ret[k] = v
    return ret


def _parse_logits(logits, length):
    logits = logits[1: length + 1, :length]
    orders = logits.argsort(descending=False).tolist()
    ret = [o.pop() for o in orders]
    while True:
        order_to_idxes = defaultdict(list)
        for idx, order in enumerate(ret):
            order_to_idxes[order].append(idx)
        order_to_idxes = {k: v for k, v in order_to_idxes.items() if len(v) > 1}
        if not order_to_idxes:
            break
        for order, idxes in order_to_idxes.items():
            idxes_to_logit = {}
            for idx in idxes:
                idxes_to_logit[idx] = logits[idx, order]
            idxes_to_logit = sorted(idxes_to_logit.items(), key=lambda x: x[1], reverse=True)
            for idx, _ in idxes_to_logit[1:]:
                ret[idx] = orders[idx].pop()
    return ret


class ReadingOrderSorter:
    def __init__(self, model_path: str):
        print(f"[排序] 加载 LayoutReader 模型: {model_path}")
        self.model = LayoutLMv3ForTokenClassification.from_pretrained(model_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[排序] 设备: {self.device}")
        self.model = self.model.to(self.device)
        self.model.eval()

    def sort(self, merged_data: dict) -> dict:
        """输入 {page_N: {page_info, blocks}}, 输出 {metadata, pages}"""
        global_order = 0
        output_pages = []

        page_items = sorted(merged_data.items(), key=lambda x: x[1]["page_info"]["page_index"])

        for page_key, page_data in page_items:
            page_idx = page_data["page_info"]["page_index"]
            # 收集所有文本框 (真实+虚拟)
            all_boxes = []
            meta = []  # (block_idx, textbox_idx_in_block)
            for bi, block in enumerate(page_data["blocks"]):
                for ti, tb in enumerate(block["contained_text_boxes"]):
                    bbox = tb["bbox"]
                    if len(bbox) >= 4:
                        all_boxes.append(tb)
                        meta.append((bi, ti))

            if not all_boxes:
                output_pages.append({
                    "page_index": page_idx,
                    "page_info": page_data["page_info"],
                    "blocks": page_data["blocks"]})
                continue
            if len(all_boxes) > MAX_LEN:
                print(f"[排序] 单页文本框 {len(all_boxes)} 超过 LayoutReader 限制，回退快速排序")
                from .fast_sorter import FastReadingOrderSorter
                return FastReadingOrderSorter().sort(merged_data)

            # 归一化坐标 → 0-1000
            page_info = page_data.get("page_info", {})
            page_w = max(1, int(page_info.get("page_width") or _max_coord(all_boxes, 2) or 1700))
            page_h = max(1, int(page_info.get("page_height") or _max_coord(all_boxes, 3) or 2200))
            boxes_norm = []
            for tb in all_boxes:
                x1 = min(1000, max(0, int(tb["bbox"][0] * 1000 / page_w)))
                y1 = min(1000, max(0, int(tb["bbox"][1] * 1000 / page_h)))
                x2 = min(1000, max(0, int(tb["bbox"][2] * 1000 / page_w)))
                y2 = min(1000, max(0, int(tb["bbox"][3] * 1000 / page_h)))
                boxes_norm.append([x1, y1, x2, y2])

            # 推理
            inputs = _boxes2inputs(boxes_norm)
            inputs = _prepare_inputs(inputs, self.model)
            with torch.no_grad():
                logits = self.model(**inputs).logits.cpu().squeeze(0)
            orders = _parse_logits(logits, len(boxes_norm))

            # 映射阅读顺序
            order_map = {}
            for ro, orig_idx in enumerate(orders):
                bi, ti = meta[orig_idx]
                order_map[(bi, ti)] = {"page_ro": ro, "global_ro": global_order}
                global_order += 1

            # 生成输出
            out_blocks = []
            for bi, block in enumerate(page_data["blocks"]):
                out_tbs = []
                block_ros = []
                for ti, tb in enumerate(block["contained_text_boxes"]):
                    tb_out = dict(tb)
                    info = order_map.get((bi, ti))
                    tb_out["page_reading_order"] = info["page_ro"] if info else -1
                    tb_out["global_reading_order"] = info["global_ro"] if info else -1
                    if info: block_ros.append(info["page_ro"])
                    out_tbs.append(tb_out)

                median_ro = statistics.median(block_ros) if block_ros else float('inf')
                out_blocks.append({
                    "block_info": dict(block["block_info"],
                                       textbox_reading_order_median=median_ro),
                    "contained_text_boxes": out_tbs
                })

            # 按中位数排序
            out_blocks.sort(key=lambda b: b["block_info"]["textbox_reading_order_median"])
            output_pages.append({
                "page_index": page_idx,
                "page_info": page_data["page_info"],
                "blocks": out_blocks
            })

        total_textboxes = sum(
            sum(len(b["contained_text_boxes"]) for b in p["blocks"])
            for p in output_pages)
        return {
            "metadata": {
                "total_pages": len(output_pages),
                "total_textboxes": total_textboxes,
                "processing_info": "blocks_ordered_by_textbox_median_reading_order"
            },
            "pages": output_pages
        }


def _max_coord(text_boxes, index):
    values = [tb["bbox"][index] for tb in text_boxes if len(tb.get("bbox", [])) > index]
    return max(values) if values else 0
