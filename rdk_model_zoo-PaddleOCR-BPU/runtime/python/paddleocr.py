# Copyright (c) 2026 D-Robotics Corporation
# Licensed under the Apache License, Version 2.0
#
# 中文版 PaddleOCR 推理封装 (基于官方 rdk_model_zoo sample 修改)
# 改动点:
#   1. _CTCLabelConverter 改为从 dict.txt 加载中文字典 (6625 类)
#   2. PaddleOCRConfig.rec_output_size = (40, 6625)
#   3. PaddleOCRConfig 增加 dict_path
#   det 仍用官方 en_PP-OCRv3_det (nv12)，rec 用中文 int16 模型 (featuremap)

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import hbm_runtime
import numpy as np
import pyclipper

sys.path.append(os.path.abspath("../../../../../"))
import utils.py_utils.preprocess as pre_utils

logger = logging.getLogger("PaddleOCR")


@dataclass
class PaddleOCRConfig:
    det_model_path: str = ""
    rec_model_path: str = ""
    dict_path: str = "./dict.txt"           # 中文字典路径
    det_threshold: float = 0.5
    det_ratio_prime: float = 2.7
    det_min_area: int = 100
    rec_input_size: Tuple[int, int] = (48, 320)
    rec_output_size: Tuple[int, int] = (40, 6625)   # 中文: T=40, C=6625


class _CTCLabelConverter:
    """中文 CTC 解码: index 0=blank, 1..6623=dict行, 6624=space。"""

    def __init__(self, dict_path: str) -> None:
        # char_table[i-1] 对应模型输出 index i (i>=1)
        self.char_table: List[str] = []
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                self.char_table.append(line.rstrip("\n").rstrip("\r"))
        self.char_table.append(" ")  # space, 总计 6624 (对应 index 1..6624)

    def decode_greedy(self, idx_seq: np.ndarray) -> str:
        """CTC greedy 解码: 跳过 blank(0), 合并连续重复。"""
        chars = []
        last = -1
        for idx in idx_seq:
            idx = int(idx)
            if idx != 0 and idx != last:
                if 1 <= idx <= len(self.char_table):
                    chars.append(self.char_table[idx - 1])
            last = idx
        return "".join(chars)


class PaddleOCR:
    def __init__(self, config: PaddleOCRConfig) -> None:
        self.cfg = config

        self.det_model = hbm_runtime.HB_HBMRuntime(config.det_model_path)
        self.det_model_name = self.det_model.model_names[0]
        self.det_input_name = self.det_model.input_names[self.det_model_name][0]
        self.det_input_shape = self.det_model.input_shapes[self.det_model_name][self.det_input_name]
        self.det_output_name = self.det_model.output_names[self.det_model_name][0]
        self.det_input_h = self.det_input_shape[2]
        self.det_input_w = self.det_input_shape[3]

        self.rec_model = hbm_runtime.HB_HBMRuntime(config.rec_model_path)
        self.rec_model_name = self.rec_model.model_names[0]
        self.rec_input_name = self.rec_model.input_names[self.rec_model_name][0]
        self.rec_output_name = self.rec_model.output_names[self.rec_model_name][0]

        self.converter = _CTCLabelConverter(config.dict_path)

    def set_scheduling_params(self, priority=None, bpu_cores=None) -> None:
        det_kwargs, rec_kwargs = {}, {}
        if priority is not None:
            det_kwargs["priority"] = {self.det_model_name: priority}
            rec_kwargs["priority"] = {self.rec_model_name: priority}
        if bpu_cores is not None:
            det_kwargs["bpu_cores"] = {self.det_model_name: bpu_cores}
            rec_kwargs["bpu_cores"] = {self.rec_model_name: bpu_cores}
        if det_kwargs:
            self.det_model.set_scheduling_params(**det_kwargs)
            self.rec_model.set_scheduling_params(**rec_kwargs)

    # ---------- Detection ----------
    def pre_process(self, image: np.ndarray) -> Dict[str, Dict[str, np.ndarray]]:
        if image is None:
            raise ValueError("Input image is None")
        resized = cv2.resize(image, (self.det_input_w, self.det_input_h))
        y, uv = pre_utils.bgr_to_nv12_planes(resized)
        nv12 = np.concatenate((y.reshape(-1), uv.reshape(-1)), axis=0).reshape(
            (1, self.det_input_h * 3 // 2, self.det_input_w, 1))
        return {self.det_model_name: {self.det_input_name: nv12.astype(np.uint8)}}

    def forward(self, input_tensor):
        return self.det_model.run(input_tensor)

    def post_process(self, outputs, image=None):
        raw = outputs[self.det_model_name][self.det_output_name]
        img_h, img_w = image.shape[:2] if image is not None else (self.det_input_h, self.det_input_w)
        preds = raw.reshape(1, self.det_input_h, self.det_input_w)
        preds = np.where(preds > self.cfg.det_threshold, 255, 0).astype(np.uint8).squeeze()
        preds = cv2.resize(preds, (img_w, img_h))
        contours, _ = cv2.findContours(preds, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dilated_polys = self._dilate_contours(contours)
        boxes_list = self._get_bounding_boxes(dilated_polys, self.cfg.det_min_area)
        return dilated_polys, boxes_list

    def _dilate_contours(self, contours):
        dilated_polys = []
        for poly in contours:
            poly = poly[:, 0, :]
            arc_length = cv2.arcLength(poly, True)
            if arc_length == 0:
                continue
            d_prime = cv2.contourArea(poly) * self.cfg.det_ratio_prime / arc_length
            pco = pyclipper.PyclipperOffset()
            pco.AddPath(poly, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            dilated_poly = np.array(pco.Execute(d_prime))
            if dilated_poly.size == 0 or dilated_poly.dtype != np.int_ or len(dilated_poly) != 1:
                continue
            dilated_polys.append(dilated_poly)
        return dilated_polys

    def _get_bounding_boxes(self, dilated_polys, min_area):
        boxes_list = []
        for cnt in dilated_polys:
            if cv2.contourArea(cnt) < min_area:
                continue
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect).astype(np.int_)
            boxes_list.append(box)
        return boxes_list

    # ---------- Recognition ----------
    def _rec_pre_process(self, cropped_img: np.ndarray) -> np.ndarray:
        h, w = self.cfg.rec_input_size
        resized = cv2.resize(cropped_img, (w, h))
        resized = (resized / 255.0).astype(np.float32)
        resized = resized[:, :, [2, 1, 0]]            # BGR -> RGB
        return resized[None].transpose(0, 3, 1, 2)     # NHWC -> NCHW

    def _rec_forward(self, input_tensor):
        return self.rec_model.run({self.rec_model_name: {self.rec_input_name: input_tensor}})

    def _rec_post_process(self, outputs) -> str:
        t, c = self.cfg.rec_output_size
        preds = outputs[self.rec_model_name][self.rec_output_name].reshape(t, c)
        idx_seq = np.argmax(preds, axis=-1)
        return self.converter.decode_greedy(idx_seq)

    @staticmethod
    def _crop_and_rotate(img, box):
        rect = cv2.minAreaRect(box)
        box_pts = cv2.boxPoints(rect).astype(np.intp)
        width = int(rect[1][0]); height = int(rect[1][1]); angle = rect[2]
        if width == 0 or height == 0:
            return img
        src_pts = box_pts.astype("float32")
        dst_pts = np.array([[0, height - 1], [0, 0], [width - 1, 0], [width - 1, height - 1]], dtype="float32")
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(img, M, (width, height))
        if angle >= 45:
            warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        return warped

    def predict(self, image):
        s1 = time.perf_counter()
        input_tensors = self.pre_process(image)
        det_outputs = self.forward(input_tensors)
        _, boxes = self.post_process(det_outputs, image)
        t1 = (time.perf_counter() - s1) * 1000

        s2 = time.perf_counter()
        texts = []
        for box in boxes:
            cropped = self._crop_and_rotate(image, box)
            rec_input = self._rec_pre_process(cropped)
            rec_outputs = self._rec_forward(rec_input)
            texts.append(self._rec_post_process(rec_outputs))
        t2 = (time.perf_counter() - s2) * 1000

        logger.info(f"Detection: {t1:.2f} ms | Recognition ({len(boxes)} boxes): {t2:.2f} ms")
        return boxes, texts

    def __call__(self, image):
        return self.predict(image)
