# core/sort_blocks.py


def sort_blocks(blocks):
    """
    兼容旧版本调用
    默认走 V4.6
    """
    return sort_blocks_v46(blocks)


def sort_blocks_v46(blocks):
    """
    V4.6 比赛级阅读顺序（Column-aware）

    思路：

    1. 检测页面中线
    2. 分左右栏
    3. 栏内按 y 排序
    4. 左栏 → 右栏

    block格式：

    {
        "type": "text",
        "box": [x1, y1, x2, y2],
        "text": [...]
    }

    或：

    {
        "type": "text",
        "bbox": [x1, y1, x2, y2]
    }
    """

    if len(blocks) == 0:
        return blocks

    # =========================
    # 自动兼容 box / bbox
    # =========================
    key_name = None

    if "box" in blocks[0]:
        key_name = "box"

    elif "bbox" in blocks[0]:
        key_name = "bbox"

    else:
        print("⚠️ 找不到 box/bbox 字段")
        return blocks

    # =========================
    # 计算页面中心线
    # =========================
    centers = []

    for b in blocks:

        x1, y1, x2, y2 = b[key_name]

        cx = (x1 + x2) / 2

        centers.append(cx)

    page_mid = sum(centers) / len(centers)

    # =========================
    # 分左右栏
    # =========================
    left_blocks = []
    right_blocks = []

    for b in blocks:

        x1, y1, x2, y2 = b[key_name]

        cx = (x1 + x2) / 2

        if cx < page_mid:
            left_blocks.append(b)
        else:
            right_blocks.append(b)

    # =========================
    # 栏内排序（从上到下）
    # =========================
    left_blocks.sort(
        key=lambda b: b[key_name][1]
    )

    right_blocks.sort(
        key=lambda b: b[key_name][1]
    )

    

    # =========================
    # 最终拼接
    # =========================
    sorted_blocks = (
        left_blocks +
        right_blocks
    )

    return sorted_blocks