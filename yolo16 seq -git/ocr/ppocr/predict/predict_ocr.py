# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：predict_ocr
# @Date   ：2024/7/31 17:51
# @Author ：leemysw

# 2024/7/31 17:51   Create
# =====================================================

import copy
import os

import cv2
import numpy as np

from .predict_cls import TextClassifier
from .predict_det import TextDetector
from .predict_rec import TextRecognizer


class OCR:
    def __init__(self, conf):
        self.conf = conf
        self.text_detector = None
        self.text_recognizer = None
        self.use_angle_cls = False
        self.drop_score = 0.5
        self.text_classifier = None
        self.crop_image_res_index = 0
        self.load_model(conf)

    def load_model(self, conf=None):
        if conf is None:
            conf = self.conf

        self.text_detector = TextDetector(conf)
        self.text_recognizer = TextRecognizer(conf)
        self.use_angle_cls = conf.use_angle_cls
        self.drop_score = conf.drop_score
        if self.use_angle_cls:
            self.text_classifier = TextClassifier(conf)

        self.conf = conf
        self.crop_image_res_index = 0

    def draw_crop_rec_res(self, output_dir, img_crop_list, rec_res):
        os.makedirs(output_dir, exist_ok=True)
        bbox_num = len(img_crop_list)
        for bno in range(bbox_num):
            cv2.imwrite(os.path.join(output_dir, f"mg_crop_{bno + self.crop_image_res_index}.jpg"), img_crop_list[bno])

        self.crop_image_res_index += bbox_num

    @staticmethod
    def formula_in_text(mf_bbox, text_bbox):
        x1, y1, x2, y2 = mf_bbox
        x3, y3 = text_bbox[0]
        x4, y4 = text_bbox[2]
        left_box, right_box = None, None
        same_line = abs((y1 + y2) / 2 - (y3 + y4) / 2) / abs(y4 - y3) < 0.2
        if not same_line:
            return False, left_box, right_box
        else:
            drop_origin = False
            left_x = x1 - 1
            right_x = x2 + 1
            if x3 < x1 and x2 < x4:
                drop_origin = True
                left_box = np.array([
                    text_bbox[0],
                    [left_x, text_bbox[1][1]],
                    [left_x, text_bbox[2][1]],
                    text_bbox[3]
                ]).astype("float32")
                right_box = np.array([
                    [right_x, text_bbox[0][1]],
                    text_bbox[1],
                    text_bbox[2],
                    [right_x, text_bbox[3][1]]
                ]).astype("float32")
            if x3 < x1 and x1 <= x4 <= x2:
                drop_origin = True
                left_box = np.array([
                    text_bbox[0],
                    [left_x, text_bbox[1][1]],
                    [left_x, text_bbox[2][1]],
                    text_bbox[3]
                ]).astype("float32")
            if x1 <= x3 <= x2 and x2 < x4:
                drop_origin = True
                right_box = np.array([
                    [right_x, text_bbox[0][1]],
                    text_bbox[1], text_bbox[2],
                    [right_x, text_bbox[3][1]]
                ]).astype("float32")
            if x1 <= x3 < x4 <= x2:
                drop_origin = True
            return drop_origin, left_box, right_box

    def update_det_boxes(self, dt_boxes, mfdetrec_res):
        new_dt_boxes = dt_boxes
        for mf_box in mfdetrec_res:
            flag, left_box, right_box = False, None, None
            for idx, text_box in enumerate(new_dt_boxes):
                ret, left_box, right_box = self.formula_in_text(mf_box['bbox'], text_box)
                if ret:
                    new_dt_boxes.pop(idx)
                    if left_box is not None:
                        new_dt_boxes.append(left_box)
                    if right_box is not None:
                        new_dt_boxes.append(right_box)
                    break

        return new_dt_boxes

    def __call__(self, img, cls=True, mfd_res=None):
        ori_im = img.copy()
        # 文字检测
        dt_boxes = self.text_detector(img)

        if dt_boxes is None:
            return None, None

        img_crop_list = []

        dt_boxes = self.sorted_boxes(dt_boxes)
        if mfd_res:
            dt_boxes = self.update_det_boxes(dt_boxes, mfd_res)

        # 图片裁剪
        for bno in range(len(dt_boxes)):
            tmp_box = copy.deepcopy(dt_boxes[bno])
            if self.conf.det_box_type == "quad":
                img_crop = self.get_rotate_crop_image(ori_im, tmp_box)
            else:
                img_crop = self.get_minarea_rect_crop(ori_im, tmp_box)
            img_crop_list.append(img_crop)

        # 方向分类
        if self.use_angle_cls and cls:
            img_crop_list, angle_list = self.text_classifier(img_crop_list)

        # 文字识别
        rec_res = self.text_recognizer(img_crop_list)
        if self.conf.save_crop_res:
            self.draw_crop_rec_res(self.conf.crop_res_save_dir, img_crop_list, rec_res)

        filter_boxes, filter_rec_res = [], []
        for box, rec_result in zip(dt_boxes, rec_res):
            text, score = rec_result
            if score >= self.drop_score:
                filter_boxes.append(box)
                filter_rec_res.append(rec_result)

        return filter_boxes, filter_rec_res

    @staticmethod
    def sorted_boxes(dt_boxes):
        """
        Sort text boxes in order from top to bottom, left to right
        conf:
            dt_boxes(array):detected text boxes with shape [4, 2]
        return:
            sorted boxes(array) with shape [4, 2]
        """
        num_boxes = dt_boxes.shape[0]
        sorted_boxes = sorted(dt_boxes, key=lambda x: (x[0][1], x[0][0]))
        _boxes = list(sorted_boxes)

        for i in range(num_boxes - 1):
            for j in range(i, -1, -1):
                if abs(_boxes[j + 1][0][1] - _boxes[j][0][1]) < 10 and \
                        (_boxes[j + 1][0][0] < _boxes[j][0][0]):
                    tmp = _boxes[j]
                    _boxes[j] = _boxes[j + 1]
                    _boxes[j + 1] = tmp
                else:
                    break
        return _boxes

    @staticmethod
    def get_rotate_crop_image(img, points):
        """
        img_height, img_width = img.shape[0:2]
        left = int(np.min(points[:, 0]))
        right = int(np.max(points[:, 0]))
        top = int(np.min(points[:, 1]))
        bottom = int(np.max(points[:, 1]))
        img_crop = img[top:bottom, left:right, :].copy()
        points[:, 0] = points[:, 0] - left
        points[:, 1] = points[:, 1] - top
        """
        assert len(points) == 4, "shape of points must be 4*2"
        img_crop_width = int(
            max(
                np.linalg.norm(points[0] - points[1]),
                np.linalg.norm(points[2] - points[3])))
        img_crop_height = int(
            max(
                np.linalg.norm(points[0] - points[3]),
                np.linalg.norm(points[1] - points[2])))
        pts_std = np.float32([[0, 0], [img_crop_width, 0],
                              [img_crop_width, img_crop_height],
                              [0, img_crop_height]])
        M = cv2.getPerspectiveTransform(points, pts_std)
        dst_img = cv2.warpPerspective(
            img,
            M, (img_crop_width, img_crop_height),
            borderMode=cv2.BORDER_REPLICATE,
            flags=cv2.INTER_CUBIC)
        dst_img_height, dst_img_width = dst_img.shape[0:2]
        if dst_img_height * 1.0 / dst_img_width >= 1.5:
            dst_img = np.rot90(dst_img)
        return dst_img

    def get_minarea_rect_crop(self, img, points):
        bounding_box = cv2.minAreaRect(np.array(points).astype(np.int32))
        points = sorted(list(cv2.boxPoints(bounding_box)), key=lambda x: x[0])

        index_a, index_b, index_c, index_d = 0, 1, 2, 3
        if points[1][1] > points[0][1]:
            index_a = 0
            index_d = 1
        else:
            index_a = 1
            index_d = 0
        if points[3][1] > points[2][1]:
            index_b = 2
            index_c = 3
        else:
            index_b = 3
            index_c = 2

        box = [points[index_a], points[index_b], points[index_c], points[index_d]]
        crop_img = self.get_rotate_crop_image(img, np.array(box))
        return crop_img
