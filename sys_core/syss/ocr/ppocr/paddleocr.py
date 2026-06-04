# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：config
# @Date   ：2024/7/31 18:15
# @Author ：leemysw

# 2024/7/31 18:15   Create
# =====================================================

import cv2
import numpy as np

from ocr_conf import OCRConfig
from predict.predict_ocr import OCR

class ONNXPaddleOcr(OCR):
    def __init__(self, **kwargs):
        # if 'cls_thresh' not in kwargs:
        #     kwargs['cls_thresh'] = 1.0
        super().__init__(OCRConfig(**kwargs))        
    def ocr(
            self,
            img,
            det=True,
            rec=True,
            cls=True,
            mfd_res=None
    ):
        if cls and not self.use_angle_cls:
            print("Since the angle classifier is not initialized, "
                  "the angle classifier will not be used during the forward process")


        if det and rec:
            ocr_res = []

            dt_boxes, rec_res = self.__call__(img, cls, mfd_res)
            tmp_res = [[box.tolist(), res] for box, res in zip(dt_boxes, rec_res)]
            # 计数dt_boxes的数量，写入output_full.md,tmp_res都写入，其中tmp每个元素之间添加换行符
            with open("param/output_full.md", "w") as f:
                f.write(str(len(dt_boxes)))
                f.write("\n")
                for i in range(len(tmp_res)):
                    f.write(str(tmp_res[i]))
                    f.write("\n")

            ocr_res.append(tmp_res)
            return ocr_res
        elif det and not rec:
            ocr_res = []
            dt_boxes = self.text_detector(img)
            dt_boxes = self.sorted_boxes(dt_boxes)

            tmp_res = [box.tolist() for box in dt_boxes]
            ocr_res.append(tmp_res)
            return ocr_res
        else:
            ocr_res = []
            cls_res = []

            if not isinstance(img, list):
                img = [img]
            if self.use_angle_cls and cls:
                img, cls_res_tmp = self.text_classifier(img)
                if not rec:
                    cls_res.append(cls_res_tmp)
            rec_res = self.text_recognizer(img)
            ocr_res.append(rec_res)

            if not rec:
                return cls_res
            return ocr_res

    def preprocess_image(self, _image, inv=False, bin=False, alpha_color=(255, 255, 255)):
        _image = self.alpha_to_color(_image, alpha_color)
        if inv:
            _image = cv2.bitwise_not(_image)
        if bin:
            _image = self.binarize_img(_image)
        return _image

    @staticmethod
    def alpha_to_color(img, alpha_color=(255, 255, 255)):
        if len(img.shape) == 3 and img.shape[2] == 4:
            B, G, R, A = cv2.split(img)
            alpha = A / 255

            R = (alpha_color[0] * (1 - alpha) + R * alpha).astype(np.uint8)
            G = (alpha_color[1] * (1 - alpha) + G * alpha).astype(np.uint8)
            B = (alpha_color[2] * (1 - alpha) + B * alpha).astype(np.uint8)

            img = cv2.merge((B, G, R))
        return img

    @staticmethod
    def binarize_img(img):
        if len(img.shape) == 3 and img.shape[2] == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # conversion to grayscale image
            # use cv2 threshold binarization
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        return img

