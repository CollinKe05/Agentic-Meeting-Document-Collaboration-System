"""DocLayout-YOLO 版面分析器"""
from dataclasses import dataclass
from typing import List
import cv2
import numpy as np
import onnxruntime as ort

from ..utils.image_utils import imread_cn

LABELS_CN = ["标题", "正文", "废弃", "图片", "图片标题", "表格", "表格标题", "表格脚注", "公式", "公式标题"]
LABELS_EN = ["title", "plain text", "abandon", "figure", "figure_caption",
             "table", "table_caption", "table_footnote", "isolate_formula", "formula_caption"]


@dataclass
class LayoutBlock:
    class_name: str
    bbox: list          # [x1, y1, x2, y2]
    score: float
    page_idx: int = 0
    block_idx: int = 0


# ── DocLayout-YOLO 预处理 ──

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


def _preprocess(image, input_size=(1024, 1024)):
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


def _multiclass_nms(boxes, scores, class_ids, iou_thres):
    keep = []
    for cls in np.unique(class_ids):
        idx = np.where(class_ids == cls)[0]
        cls_keep = _nms(boxes[idx], scores[idx], iou_thres)
        keep.extend(idx[cls_keep])
    return keep


def _nms(boxes, scores, iou_thres):
    order = np.argsort(scores)[::-1]
    keep = []
    while len(order) > 0:
        keep.append(order[0])
        if len(order) == 1: break
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


def _postprocess(preds, labels, ori_shape, input_size=(1024, 1024), conf_thres=0.2, iou_thres=0.5):
    preds = preds[0]
    mask = preds[..., 4] > conf_thres
    preds = preds[mask]
    if len(preds) == 0: return [], [], []
    preds[:, :4] = _scale_boxes(input_size, preds[:, :4], ori_shape)
    boxes, scores = preds[:, :4], preds[:, 4]
    class_ids = preds[:, 5].astype(int)
    result_labels = [labels[i] if i < len(labels) else f"class_{i}" for i in class_ids]
    keep = _multiclass_nms(boxes, scores, class_ids, iou_thres)
    return boxes[keep], scores[keep], [result_labels[i] for i in keep]


def _get_model_labels(session):
    try:
        meta = session.get_modelmeta().custom_metadata_map
        if "character" in meta: return meta["character"].splitlines()
    except: pass
    return LABELS_CN


class LayoutAnalyzer:
    def __init__(self, model_path: str, conf_thres=0.2, iou_thres=0.5, labels="cn", input_size=1024):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.input_size = (input_size, input_size)
        model_labels = _get_model_labels(self.session)
        self.labels = LABELS_CN if labels == "cn" else LABELS_EN
        if len(model_labels) == len(LABELS_EN):
            self.labels = LABELS_CN if labels == "cn" else model_labels

    def analyze(self, image: np.ndarray, page_idx: int = 0) -> List[LayoutBlock]:
        tensor = _preprocess(image, self.input_size)
        outputs = self.session.run([self.output_name], {self.input_name: tensor})
        boxes, scores, names = _postprocess(
            outputs, self.labels, image.shape[:2], self.input_size, self.conf_thres, self.iou_thres)
        return [LayoutBlock(
            class_name=name, bbox=box.astype(int).tolist(),
            score=float(score), page_idx=page_idx, block_idx=i
        ) for i, (box, score, name) in enumerate(zip(boxes, scores, names))]

    def analyze_images(self, images: List[np.ndarray]) -> List[List[LayoutBlock]]:
        return [self.analyze(img, i) for i, img in enumerate(images)]
