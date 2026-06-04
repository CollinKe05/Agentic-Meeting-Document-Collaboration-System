"""快速阅读排序 — 基于坐标启发式 (支持多栏)"""
import statistics


def _line_similar(box_a, box_b, threshold):
    """两个框是否在同一行"""
    a_mid = (box_a[1] + box_a[3]) / 2
    b_mid = (box_b[1] + box_b[3]) / 2
    a_h = box_a[3] - box_a[1]
    b_h = box_b[3] - box_b[1]
    avg_h = (a_h + b_h) / 2
    if avg_h <= 0:
        return False
    return abs(a_mid - b_mid) / avg_h < threshold


def _detect_columns(all_boxes, gap_ratio=0.12):
    """检测多栏布局 — 找页面中间区域的最大间隙"""
    if len(all_boxes) < 4:
        return []

    x_centers = sorted((b[0] + b[2]) / 2 for b in all_boxes)
    all_x = [b[0] for b in all_boxes] + [b[2] for b in all_boxes]
    page_min, page_max = min(all_x), max(all_x)
    page_w = page_max - page_min if page_max > page_min else 1

    # 只考虑页面中间 20%-80% 区域的分割点，忽略边缘间隙
    best_gap = 0
    best_split = 0
    for i in range(1, len(x_centers)):
        mid = (x_centers[i] + x_centers[i - 1]) / 2
        # 分割点必须在页面中间区域
        rel_pos = (mid - page_min) / page_w
        if rel_pos < 0.2 or rel_pos > 0.8:
            continue
        gap = x_centers[i] - x_centers[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_split = mid

    # 间隙大于阈值 → 分栏
    if best_gap > page_w * gap_ratio:
        # 确保两边都有足够的框 (至少 15%)
        left_count = sum(1 for x in x_centers if x < best_split)
        right_count = len(x_centers) - left_count
        if left_count >= len(x_centers) * 0.15 and right_count >= len(x_centers) * 0.15:
            return [best_split]

    return []


def _sort_boxes_in_region(boxes, line_overlap):
    """区域内按行排序: 行从上到下, 行内从左到右"""
    if not boxes:
        return []

    # 按 y 分组为行
    sorted_idx = sorted(range(len(boxes)), key=lambda i: boxes[i][1])
    lines = []
    for idx in sorted_idx:
        box = boxes[idx]
        placed = False
        for line in lines:
            if _line_similar(box, line[0], line_overlap):
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])

    # 每行内从左到右
    for line in lines:
        line.sort(key=lambda b: b[0])

    # 行从上到下
    lines.sort(key=lambda ln: ln[0][1])

    return [box for line in lines for box in line]


class FastReadingOrderSorter:
    """基于坐标的快速排序 — 自动检测多栏，每栏从上到下，从左到右"""

    def __init__(self, line_overlap: float = 0.4):
        self.line_overlap = line_overlap

    def sort(self, merged_data: dict) -> dict:
        global_order = 0
        output_pages = []

        page_items = sorted(merged_data.items(), key=lambda x: x[1]["page_info"]["page_index"])

        for page_key, page_data in page_items:
            page_idx = page_data["page_info"]["page_index"]

            # 收集所有文本框
            all_boxes = []
            meta = []
            for bi, block in enumerate(page_data["blocks"]):
                for ti, tb in enumerate(block["contained_text_boxes"]):
                    bbox = tb["bbox"]
                    if len(bbox) >= 4:
                        all_boxes.append(bbox)
                        meta.append((bi, ti))

            if not all_boxes:
                output_pages.append({
                    "page_index": page_idx,
                    "page_info": page_data["page_info"],
                    "blocks": page_data["blocks"]})
                continue

            # 检测分栏 (间隙 > 页面宽度12%)
            splits = _detect_columns(all_boxes)

            if splits:
                # 多栏: 分离跨栏元素(标题等) + 左栏 + 右栏
                split_x = splits[0]
                page_w = max(b[2] for b in all_boxes) - min(b[0] for b in all_boxes)

                # block 级别: 宽度 > 55% 页宽 → 通栏
                spanning_blocks = set()
                for bi, block in enumerate(page_data["blocks"]):
                    bb = block["block_info"]["bbox"]
                    if (bb[2] - bb[0]) > page_w * 0.55:
                        spanning_blocks.add(bi)

                spanning = []
                left_items = []
                right_items = []
                for i, b in enumerate(all_boxes):
                    bi = meta[i][0]
                    if bi in spanning_blocks:
                        spanning.append((b, i))
                    elif (b[0] + b[2]) / 2 < split_x:
                        left_items.append((b, i))
                    else:
                        right_items.append((b, i))

                spanning_sorted = _sort_boxes_in_region([b for b, _ in spanning], self.line_overlap)
                left_sorted = _sort_boxes_in_region([b for b, _ in left_items], self.line_overlap)
                right_sorted = _sort_boxes_in_region([b for b, _ in right_items], self.line_overlap)

                # 跨栏元素 → 左栏 → 右栏
                ordered_boxes = spanning_sorted + left_sorted + right_sorted
            else:
                # 单栏
                ordered_boxes = _sort_boxes_in_region(all_boxes, self.line_overlap)

            # 分配阅读顺序 (匹配回原始索引)
            orders = []
            for box in ordered_boxes:
                for i, b in enumerate(all_boxes):
                    if b == box:
                        orders.append(i)
                        break

            # 映射
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
                    if info:
                        block_ros.append(info["page_ro"])
                    out_tbs.append(tb_out)

                median_ro = statistics.median(block_ros) if block_ros else float("inf")
                out_blocks.append({
                    "block_info": dict(block["block_info"],
                                       textbox_reading_order_median=median_ro),
                    "contained_text_boxes": out_tbs
                })

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
                "processing_info": "coordinate_based_reading_order_with_column_detection"
            },
            "pages": output_pages
        }
