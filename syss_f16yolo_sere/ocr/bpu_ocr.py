"""BPU OCR (RDK X5) — 使用 hbm_runtime"""
from pathlib import Path
import numpy as np
import cv2

from .base import BaseOCR, PageOCRResult, OCRResult


class BPUOCR(BaseOCR):
    def __init__(self, det_model: str, rec_model: str, char_dict: str,
                 rec_thresh: float = 0.5, det_thresh: float = 0.5):
        import hbm_runtime

        self.rec_thresh = rec_thresh

        # 检测模型
        self.det_model = hbm_runtime.HB_HBMRuntime(det_model)
        self.det_name = self.det_model.model_names[0]
        self.det_input = self.det_model.input_names[self.det_name][0]
        self.det_output = self.det_model.output_names[self.det_name][0]
        det_shape = self.det_model.input_shapes[self.det_name][self.det_input]
        self.det_h, self.det_w = det_shape[2], det_shape[3]

        # 识别模型
        self.rec_model = hbm_runtime.HB_HBMRuntime(rec_model)
        self.rec_name = self.rec_model.model_names[0]
        self.rec_input = self.rec_model.input_names[self.rec_name][0]
        self.rec_output = self.rec_model.output_names[self.rec_name][0]
        rec_shape = self.rec_model.input_shapes[self.rec_name][self.rec_input]
        self.rec_h, self.rec_w = rec_shape[2], rec_shape[3]

        # 中文字典
        self.char_table = []
        if Path(char_dict).exists():
            with open(char_dict, "r", encoding="utf-8") as f:
                self.char_table = [line.rstrip("\n\r") for line in f]
            self.char_table.append(" ")  # space

        self.det_thresh = det_thresh

    def _preprocess_det(self, image):
        """BGR → 缩放到检测模型尺寸 → NV12"""
        resized = cv2.resize(image, (self.det_w, self.det_h))
        # BGR to NV12 planes
        y_plane = cv2.cvtColor(resized, cv2.COLOR_BGR2YUV_I420)[:self.det_h, :]
        uv_h = self.det_h // 2
        uv_plane = cv2.cvtColor(resized, cv2.COLOR_BGR2YUV_I420)[self.det_h:self.det_h + uv_h, :]
        nv12 = np.concatenate((y_plane.reshape(-1), uv_plane.reshape(-1))).reshape(
            1, self.det_h * 3 // 2, self.det_w, 1).astype(np.uint8)
        return {self.det_name: {self.det_input: nv12}}

    def _postprocess_det(self, outputs, image):
        """解码检测输出 → 文本框列表"""
        raw = outputs[self.det_name][self.det_output]
        h, w = image.shape[:2]
        preds = raw.reshape(1, self.det_h, self.det_w)
        preds = np.where(preds > self.det_thresh, 255, 0).astype(np.uint8).squeeze()
        preds = cv2.resize(preds, (w, h))
        contours, _ = cv2.findContours(preds, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for cnt in contours:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect).astype(np.int_)
            boxes.append(box)
        return boxes

    def _rec_preprocess(self, crop):
        """裁剪图 → 识别模型输入 (featuremap)"""
        resized = cv2.resize(crop, (self.rec_w, self.rec_h))
        resized = (resized / 255.0).astype(np.float32)
        resized = resized[:, :, [2, 1, 0]]  # BGR → RGB
        return resized[None].transpose(0, 3, 1, 2)  # NHWC → NCHW

    def _rec_postprocess(self, outputs):
        """CTC greedy decode — 自动适配输出尺寸"""
        raw = outputs[self.rec_name][self.rec_output]
        total = raw.size
        # 常见: [seq_len, num_classes], seq_len = input_w / 8
        seq_len = self.rec_w // 8
        num_classes = total // seq_len
        if seq_len * num_classes != total:
            # 尝试交换维度
            num_classes = total // seq_len if total % seq_len == 0 else seq_len
        preds = raw.reshape(-1, num_classes)
        idx_seq = np.argmax(preds, axis=-1)
        chars = []
        last = -1
        for idx in idx_seq:
            idx = int(idx)
            if idx != 0 and idx != last:
                if 1 <= idx <= len(self.char_table):
                    chars.append(self.char_table[idx - 1])
            last = idx
        return "".join(chars)

    def process_image(self, image: np.ndarray, page_idx: int = 0) -> PageOCRResult:
        # 检测
        det_input = self._preprocess_det(image)
        det_outputs = self.det_model.run(det_input)
        boxes = self._postprocess_det(det_outputs, image)

        # 识别每个文本框
        results = []
        for box in boxes:
            # 裁剪 + 透视矫正
            rect = cv2.minAreaRect(box)
            width, height = int(rect[1][0]), int(rect[1][1])
            if width == 0 or height == 0:
                continue
            src_pts = box.astype("float32")
            dst_pts = np.array([[0, height - 1], [0, 0], [width - 1, 0],
                                [width - 1, height - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            cropped = cv2.warpPerspective(image, M, (width, height))
            if rect[2] >= 45:
                cropped = cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)

            rec_input = self._rec_preprocess(cropped)
            rec_outputs = self.rec_model.run({self.rec_name: {self.rec_input: rec_input}})
            text = self._rec_postprocess(rec_outputs)

            xs = [p[0] for p in box]; ys = [p[1] for p in box]
            results.append(OCRResult(
                bbox=[int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                transcription=text, score=1.0))

        return PageOCRResult(page_idx=page_idx, results=results)
