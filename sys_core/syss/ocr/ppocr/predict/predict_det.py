# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：predict_det
# @Date   ：2024/7/31 17:49
# @Author ：leemysw

# 2024/7/31 17:49   Create
# =====================================================

from .predict_base import PredictBase
from process.operators import *
from process.postprocess_db import DBPostProcess


class TextDetector(PredictBase):
    def __init__(self, conf):
        super(TextDetector, self).__init__()
        self.conf = conf
        self.det_algorithm = conf.det_algorithm
        pre_process_list = [
            {
                'DetResizeForTest': {
                    'limit_side_len': conf.det_limit_side_len,
                    'limit_type': conf.det_limit_type,
                }
            },
            {
                'NormalizeImage': {
                    'std': [0.229, 0.224, 0.225],
                    'mean': [0.485, 0.456, 0.406],
                    'scale': '1./255.',
                    'order': 'hwc'
                }
            },
            {
                'ToCHWImage': None
            },
            {
                'KeepKeys': {
                    'keep_keys': ['image', 'shape']
                }
            }
        ]
        postprocess_params = {
            'name': 'DBPostProcess',
            "thresh": conf.det_db_thresh,
            "box_thresh": conf.det_db_box_thresh,
            "max_candidates": 1000,
            "unclip_ratio": conf.det_db_unclip_ratio,
            "use_dilation": conf.use_dilation,
            "score_mode": conf.det_db_score_mode,
            "box_type": conf.det_box_type
        }

        # 实例化预处理操作类
        self.preprocess_op = self.create_operators(pre_process_list)
        # self.postprocess_op = build_post_process(postprocess_params)
        # 实例化后处理操作类
        self.postprocess_op = DBPostProcess(**postprocess_params)

        # 初始化模型
        self.det_onnx_session = self.get_onnx_session(conf.det_model_dir, conf.use_gpu)
        self.det_input_name = self.get_input_name(self.det_onnx_session)
        self.det_output_name = self.get_output_name(self.det_onnx_session)

    def order_points_clockwise(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        tmp = np.delete(pts, (np.argmin(s), np.argmax(s)), axis=0)
        diff = np.diff(np.array(tmp), axis=1)
        rect[1] = tmp[np.argmin(diff)]
        rect[3] = tmp[np.argmax(diff)]
        return rect

    def filter_tag_det_res(self, dt_boxes, image_shape):
        img_height, img_width = image_shape[0:2]
        dt_boxes_new = []
        for box in dt_boxes:
            if type(box) is list:
                box = np.array(box)
            box = self.order_points_clockwise(box)
            box = self.clip_det_res(box, img_height, img_width)
            rect_width = int(np.linalg.norm(box[0] - box[1]))
            rect_height = int(np.linalg.norm(box[0] - box[3]))
            if rect_width <= 3 or rect_height <= 3:
                continue
            dt_boxes_new.append(box)
        dt_boxes = np.array(dt_boxes_new)
        return dt_boxes

    def filter_tag_det_res_only_clip(self, dt_boxes, image_shape):
        img_height, img_width = image_shape[0:2]
        dt_boxes_new = []
        for box in dt_boxes:
            if type(box) is list:
                box = np.array(box)
            box = self.clip_det_res(box, img_height, img_width)
            dt_boxes_new.append(box)
        dt_boxes = np.array(dt_boxes_new)
        return dt_boxes

    @staticmethod
    def clip_det_res(points, img_height, img_width):
        for pno in range(points.shape[0]):
            points[pno, 0] = int(min(max(points[pno, 0], 0), img_width - 1))
            points[pno, 1] = int(min(max(points[pno, 1], 0), img_height - 1))
        return points

    @staticmethod
    def transform(data, ops=None):
        """ transform """
        if ops is None:
            ops = []
        for op in ops:
            data = op(data)
            if data is None:
                return None
        return data

    @staticmethod
    def create_operators(op_param_list, global_config=None):
        assert isinstance(op_param_list, list), "operator config should be a list"
        ops = []
        for operator in op_param_list:
            assert isinstance(operator, dict) and len(operator) == 1, "yaml format error"
            op_name = list(operator)[0]
            param = {} if operator[op_name] is None else operator[op_name]
            if global_config is not None:
                param.update(global_config)
            op = eval(op_name)(**param)
            ops.append(op)
        return ops

    def __call__(self, img):
        ori_im = img.copy()
        data = {'image': img}

        data = self.transform(data, self.preprocess_op)
        img, shape_list = data
        if img is None:
            return None, 0
        img = np.expand_dims(img, axis=0)
        shape_list = np.expand_dims(shape_list, axis=0)
        img = img.copy()

        input_feed = self.get_input_feed(self.det_input_name, img)
        outputs = self.det_onnx_session.run(self.det_output_name, input_feed=input_feed)

        preds = {}
        preds['maps'] = outputs[0]

        post_result = self.postprocess_op(preds, shape_list)
        dt_boxes = post_result[0]['points']

        if self.conf.det_box_type == 'poly':
            dt_boxes = self.filter_tag_det_res_only_clip(dt_boxes, ori_im.shape)
        else:
            dt_boxes = self.filter_tag_det_res(dt_boxes, ori_im.shape)

        return dt_boxes