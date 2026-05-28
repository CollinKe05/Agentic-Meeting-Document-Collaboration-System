import cv2
import numpy as np
import onnxruntime as ort
import os

from core.sort_blocks import sort_blocks


# =========================
# 全局模型（只加载一次）
# =========================
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

det_sess = ort.InferenceSession(
    os.path.join(MODEL_DIR, "det.onnx"),
    providers=["CPUExecutionProvider"]
)

rec_sess = ort.InferenceSession(
    os.path.join(MODEL_DIR, "rec.onnx"),
    providers=["CPUExecutionProvider"]
)

# 字符字典 (index 0 = CTC blank, index 1+ = dict chars)
DICT_PATH = os.path.join(os.path.dirname(__file__), "dict.txt")
with open(DICT_PATH, "r", encoding="utf-8") as f:
    char_dict = ["[blank]"] + [line.rstrip("\n").rstrip("\r") for line in f.readlines()]


# =========================
# Detection
# =========================
DET_INPUT_SIZE = 960
DET_THRESH = 0.3
DET_BOX_THRESH = 0.5
UNCLIP_RATIO = 1.5
MIN_BOX_SIZE = 8


def det_preprocess(img):
    """resize到960×960, 归一化, CHW"""
    h, w = img.shape[:2]
    ratio_h = DET_INPUT_SIZE / h
    ratio_w = DET_INPUT_SIZE / w

    img_resized = cv2.resize(img, (DET_INPUT_SIZE, DET_INPUT_SIZE))
    img_float = img_resized.astype(np.float32) / 255.0
    img_chw = np.transpose(img_float, (2, 0, 1))
    img_batch = np.expand_dims(img_chw, axis=0)

    return img_batch, (h, w), (ratio_w, ratio_h)


def det_postprocess(output, original_shape):
    """概率图 → 二值化 → 轮廓 → 边界框"""
    score_map = output[0, 0]  # (960, 960)

    # 二值化
    mask = (score_map > DET_THRESH).astype(np.uint8)

    # 找轮廓
    contours, _ = cv2.findContours(
        mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = original_shape
    ratio_w = w / DET_INPUT_SIZE
    ratio_h = h / DET_INPUT_SIZE

    boxes = []
    for cnt in contours:
        # 轮廓面积太小则跳过
        if cv2.contourArea(cnt) < MIN_BOX_SIZE * MIN_BOX_SIZE:
            continue

        # 最小外接矩形 + unclip
        rect = cv2.minAreaRect(cnt)
        cx, cy, bw, bh, angle = rect

        bw = max(bw * UNCLIP_RATIO, MIN_BOX_SIZE)
        bh = max(bh * UNCLIP_RATIO, MIN_BOX_SIZE)

        # 获取四个角点
        box = cv2.boxPoints((cx, cy, bw, bh, angle))
        box = np.array(box, dtype=np.float32)

        # 缩放回原图坐标
        box[:, 0] *= ratio_w
        box[:, 1] *= ratio_h

        # 裁剪到图像边界
        box[:, 0] = np.clip(box[:, 0], 0, w - 1)
        box[:, 1] = np.clip(box[:, 1], 0, h - 1)

        boxes.append(box)

    return boxes


def boxes_from_bitmap(output, original_shape):
    """简化版后处理: 二值化 → 轮廓 → boundingRect → unclip"""
    score_map = output[0, 0]

    mask = (score_map > DET_BOX_THRESH).astype(np.uint8)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = original_shape
    ratio_w = w / DET_INPUT_SIZE
    ratio_h = h / DET_INPUT_SIZE

    boxes = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)

        # unclip
        cx = x + bw / 2
        cy = y + bh / 2
        bw = max(bw * UNCLIP_RATIO, MIN_BOX_SIZE)
        bh = max(bh * UNCLIP_RATIO, MIN_BOX_SIZE)

        x1 = max(0, int((cx - bw / 2) * ratio_w))
        y1 = max(0, int((cy - bh / 2) * ratio_h))
        x2 = min(w - 1, int((cx + bw / 2) * ratio_w))
        y2 = min(h - 1, int((cy + bh / 2) * ratio_h))

        if x2 - x1 < MIN_BOX_SIZE or y2 - y1 < MIN_BOX_SIZE:
            continue

        boxes.append([x1, y1, x2, y2])

    return boxes


# =========================
# Recognition
# =========================
REC_INPUT_H = 48
REC_INPUT_W = 320


def rec_preprocess(crop_img):
    """裁剪图 → resize 48×320 → 归一化 → CHW"""
    img = cv2.resize(crop_img, (REC_INPUT_W, REC_INPUT_H))
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    img = np.expand_dims(img, axis=0)
    return img


def ctc_decode(output, char_list):
    """
    CTC greedy decode.
    output shape: (1, time_steps, num_classes)
    """
    pred = np.argmax(output[0], axis=-1)  # (time_steps,)

    last = -1
    chars = []
    for idx in pred:
        if idx != last and idx != 0:
            if idx < len(char_list):
                chars.append(char_list[idx])
        last = idx

    return "".join(chars)


# =========================
# 主流程
# =========================
def process_image(img_path):
    """
    ONNX OCR pipeline:
    1. 检测 → 文本框
    2. 每个框 → 识别
    3. 阅读顺序排序
    """
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError(f"Cannot read image: {img_path}")

    # ===== Step1: 检测 =====
    det_input, original_shape, _ = det_preprocess(img)

    det_input_name = det_sess.get_inputs()[0].name
    det_output = det_sess.run(None, {det_input_name: det_input})[0]

    boxes = boxes_from_bitmap(det_output, original_shape)

    # ===== Step2: 逐框识别 =====
    rec_input_name = rec_sess.get_inputs()[0].name

    blocks = []
    for box in boxes:
        x1, y1, x2, y2 = box
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        rec_input = rec_preprocess(crop)
        rec_output = rec_sess.run(None, {rec_input_name: rec_input})[0]

        text = ctc_decode(rec_output, char_dict)
        if text.strip():
            blocks.append({
                "type": "text",
                "box": [int(x1), int(y1), int(x2), int(y2)],
                "text": [text]
            })

    # ===== Step3: 阅读顺序 =====
    sorted_blocks = sort_blocks(blocks)
    return sorted_blocks
