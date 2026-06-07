"""版面分析器 —— 自动适配 DocLayout-YOLO(v10) 与 yolov8(general6)"""
from dataclasses import dataclass
from typing import List
import cv2
import numpy as np
import onnxruntime as ort

from ..utils.image_utils import imread_cn

# DocLayout-YOLO (v10) 10 类
LABELS_CN = ["标题", "正文", "废弃", "图片", "图片标题", "表格", "表格标题", "表格脚注", "公式", "公式标题"]
LABELS_EN = ["title", "plain text", "abandon", "figure", "figure_caption",
             "table", "table_caption", "table_footnote", "isolate_formula", "formula_caption"]

# yolov8 general6 6 类 -> 映射到与 DocLayout 兼容的标签词汇(下游靠这些英文名分流)
G6_EN = {0: "plain text", 1: "title", 2: "figure", 3: "table", 4: "figure_caption", 5: "isolate_formula"}
G6_CN = {0: "正文", 1: "标题", 2: "图片", 3: "表格", 4: "图片标题", 5: "公式"}


@dataclass
class LayoutBlock:
    class_name: str
    bbox: list          # [x1, y1, x2, y2]
    score: float
    page_idx: int = 0
    block_idx: int = 0


# ══════════ DocLayout-YOLO (v10) 路径 ══════════

class LetterBox:
    def __init__(self, new_shape=(1024, 1024)):
        self.new_shape = new_shape
    def __call__(self, image):
        shape = image.shape[:2]
        r = min(self.new_shape[0] / shape[0], self.new_shape[1] / shape[1])
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw = self.new_shape[1] - new_unpad[0]
        dh = self.new_shape[0] - new_unpad[1]
        img = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)
        top, bottom = int(round(dh / 2 - 0.1)), int(round(dh / 2 + 0.1))
        left, right = int(round(dw / 2 - 0.1)), int(round(dw / 2 + 0.1))
        return cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))


def _preprocess_v10(image, input_size=(1024, 1024)):
    img = LetterBox(new_shape=input_size)(image)
    img = img[..., ::-1].transpose(2, 0, 1)
    img = np.ascontiguousarray(img)
    return img[np.newaxis, ...].astype(np.float32) / 255.0


def _scale_boxes(img1_shape, boxes, img0_shape):
    gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
    pad = (round((img1_shape[1] - img0_shape[1] * gain) / 2 - 0.1),
           round((img1_shape[0] - img0_shape[0] * gain) / 2 - 0.1))
    boxes[..., 0] -= pad[0]; boxes[..., 1] -= pad[1]
    boxes[..., 2] -= pad[0]; boxes[..., 3] -= pad[1]
    boxes[..., :4] /= gain
    boxes[..., [0, 2]] = boxes[..., [0, 2]].clip(0, img0_shape[1])
    boxes[..., [1, 3]] = boxes[..., [1, 3]].clip(0, img0_shape[0])
    return boxes


def _postprocess_v10(preds, labels, ori_shape, input_size, conf_thres, iou_thres):
    preds = preds[0]
    mask = preds[..., 4] > conf_thres
    preds = preds[mask]
    if len(preds) == 0:
        return [], [], []
    preds[:, :4] = _scale_boxes(input_size, preds[:, :4], ori_shape)
    boxes, scores = preds[:, :4], preds[:, 4]
    class_ids = preds[:, 5].astype(int)
    result_labels = [labels[i] if i < len(labels) else f"class_{i}" for i in class_ids]
    keep = _multiclass_nms(boxes, scores, class_ids, iou_thres)
    return boxes[keep], scores[keep], [result_labels[i] for i in keep]


# ══════════ yolov8 (general6) 路径 ══════════

def _preprocess_yolov8(image, size=640):
    img = cv2.resize(image, (size, size))               # 直接 resize(general6 训练一致)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return np.ascontiguousarray(img.transpose(2, 0, 1)[None])


def _xywh2xyxy(b):
    y = b.copy()
    y[..., 0] = b[..., 0] - b[..., 2] / 2
    y[..., 1] = b[..., 1] - b[..., 3] / 2
    y[..., 2] = b[..., 0] + b[..., 2] / 2
    y[..., 3] = b[..., 1] + b[..., 3] / 2
    return y


def _postprocess_yolov8(preds, labels_map, ori_shape, size, conf_thres, iou_thres, nc):
    pred = np.squeeze(preds[0]).T                       # [8400, 4+nc]
    scores = pred[:, 4:4 + nc].max(1)
    m = scores > conf_thres
    pred, scores = pred[m], scores[m]
    if len(pred) == 0:
        return [], [], []
    class_ids = pred[:, 4:4 + nc].argmax(1)
    H0, W0 = ori_shape
    boxes = pred[:, :4] / size * np.array([W0, H0, W0, H0])   # 640 -> 原图(拉伸还原)
    boxes = _xywh2xyxy(boxes)
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, W0)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, H0)
    keep = _multiclass_nms(boxes, scores, class_ids, iou_thres)
    names = [labels_map.get(int(class_ids[i]), f"class_{int(class_ids[i])}") for i in keep]
    return boxes[keep], scores[keep], names


# ══════════ 公共 NMS ══════════

def _multiclass_nms(boxes, scores, class_ids, iou_thres):
    keep = []
    for cls in np.unique(class_ids):
        idx = np.where(class_ids == cls)[0]
        keep.extend(idx[_nms(boxes[idx], scores[idx], iou_thres)])
    return keep


def _nms(boxes, scores, iou_thres):
    order = np.argsort(scores)[::-1]
    keep = []
    while len(order) > 0:
        keep.append(order[0])
        if len(order) == 1:
            break
        ious = _box_iou(boxes[order[0]], boxes[order[1:]])
        order = order[1:][ious < iou_thres]
    return keep


def _box_iou(box, boxes):
    x1, y1 = np.maximum(box[0], boxes[:, 0]), np.maximum(box[1], boxes[:, 1])
    x2, y2 = np.minimum(box[2], boxes[:, 2]), np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    area_boxes = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return inter / (area_box + area_boxes - inter + 1e-5)


# ══════════ 分析器 ══════════

class LayoutAnalyzer:
    def __init__(self, model_path: str, conf_thres=0.2, iou_thres=0.5, labels="cn", input_size=None):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.labels_mode = labels

        # 自动识别模型类型:跑一次 dummy 推理看输出形状
        in_shape = self.session.get_inputs()[0].shape          # [1,3,H,W]
        side = in_shape[2] if isinstance(in_shape[2], int) else 1024
        dummy = np.zeros((1, 3, side, side), dtype=np.float32)
        out = self.session.run([self.output_name], {self.input_name: dummy})[0]
        # v10: [1,N,6](最后维6); yolov8: [1,4+nc,8400](中维小、末维大)
        if out.ndim == 3 and out.shape[1] < out.shape[2] and out.shape[1] <= 84:
            self.mode = "yolov8"
            self.input_size = (side, side)                     # general6=640
            self.nc = out.shape[1] - 4
            self.labels_map = G6_CN if labels == "cn" else G6_EN
        else:
            self.mode = "v10"
            self.input_size = (1024, 1024)
            self.labels = LABELS_CN if labels == "cn" else LABELS_EN

    def analyze(self, image: np.ndarray, page_idx: int = 0) -> List[LayoutBlock]:
        if self.mode == "yolov8":
            tensor = _preprocess_yolov8(image, self.input_size[0])
            outputs = self.session.run([self.output_name], {self.input_name: tensor})
            boxes, scores, names = _postprocess_yolov8(
                outputs, self.labels_map, image.shape[:2], self.input_size[0],
                self.conf_thres, self.iou_thres, self.nc)
        else:
            tensor = _preprocess_v10(image, self.input_size)
            outputs = self.session.run([self.output_name], {self.input_name: tensor})
            boxes, scores, names = _postprocess_v10(
                outputs, self.labels, image.shape[:2], self.input_size,
                self.conf_thres, self.iou_thres)
        return [LayoutBlock(
            class_name=name, bbox=box.astype(int).tolist(),
            score=float(score), page_idx=page_idx, block_idx=i
        ) for i, (box, score, name) in enumerate(zip(boxes, scores, names))]

    def analyze_images(self, images: List[np.ndarray]) -> List[List[LayoutBlock]]:
        return [self.analyze(img, i) for i, img in enumerate(images)]
