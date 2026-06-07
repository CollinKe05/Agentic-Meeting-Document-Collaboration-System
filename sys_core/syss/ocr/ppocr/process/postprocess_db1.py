# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：postprocess_db
# @Date   ：2024/7/31 17:54
# @Author ：leemysw

# 2024/7/31 17:54   Create
# =====================================================

import cv2
import numpy as np
import pyclipper
from shapely.geometry import Polygon


class DBPostProcess(object):
    def __init__(self,
                 thresh=0.3,
                 box_thresh=0.7,
                 max_candidates=1000,
                 unclip_ratio=2.0,
                 use_dilation=False,
                 score_mode="fast",
                 box_type='quad',
                 box_score_thres_delta=0.02,  # 添加容差参数
                 min_size_delta=0,           # 尺寸容差
                 **kwargs):
        self.thresh = thresh
        self.box_thresh = box_thresh
        self.box_score_thres_delta = box_score_thres_delta  # 边界情况的分数容差
        self.max_candidates = max_candidates
        self.unclip_ratio = unclip_ratio
        self.min_size = 3
        self.min_size_delta = min_size_delta  # 最小尺寸容差
        self.score_mode = score_mode
        self.box_type = box_type
        assert score_mode in [
            "slow", "fast"
        ], "Score mode must be in [slow, fast] but got: {}".format(score_mode)

        self.dilation_kernel = None if not use_dilation else np.array(
            [[1, 1], [1, 1]])

    def polygons_from_bitmap(self, pred, _bitmap, dest_width, dest_height):
        '''
        _bitmap: single map with shape (1, H, W),
            whose values are binarized as {0, 1}
        '''

        bitmap = _bitmap
        height, width = bitmap.shape

        boxes = []
        scores = []

        contours, _ = cv2.findContours((bitmap * 255).astype(np.uint8),
                                       cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours[:self.max_candidates]:
            epsilon = 0.002 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            points = approx.reshape((-1, 2))
            if points.shape[0] < 4:
                continue

            score = self.box_score_fast(pred, points.reshape(-1, 2))
            if self.box_thresh > score:
                continue

            if self.box_thresh > score > (self.box_thresh - self.box_score_thres_delta):
                # 对于边界分数的样本，进行更严格的多边形质量检查
                # 或者应用容差处理
                quality_score = self.assess_polygon_quality(box)
                if quality_score < 0.8:  # 质量阈值可调整
                    continue

            if points.shape[0] > 2:
                box = self.unclip(points, self.unclip_ratio)
                if len(box) > 1:
                    continue
            else:
                continue
            box = box.reshape(-1, 2)

            _, sside = self.get_mini_boxes(box.reshape((-1, 1, 2)))
            if sside < self.min_size + 2:
                continue

            box = np.array(box)
            box[:, 0] = np.clip(
                np.round(box[:, 0] / width * dest_width), 0, dest_width)
            box[:, 1] = np.clip(
                np.round(box[:, 1] / height * dest_height), 0, dest_height)
            boxes.append(box.tolist())
            scores.append(score)
        return boxes, scores

    def boxes_from_bitmap(self, pred, _bitmap, dest_width, dest_height):
        """
        _bitmap: single map with shape (1, H, W),
                whose values are binarized as {0, 1}
        """

        bitmap = _bitmap
        height, width = bitmap.shape

        outs = cv2.findContours((bitmap * 255).astype(np.uint8), cv2.RETR_LIST,
                                cv2.CHAIN_APPROX_SIMPLE)
        if len(outs) == 3:
            img, contours, _ = outs[0], outs[1], outs[2]
        elif len(outs) == 2:
            contours, _ = outs[0], outs[1]

        num_contours = min(len(contours), self.max_candidates)

        boxes = []
        scores = []
        for index in range(num_contours):
            contour = contours[index]
            points, sside = self.get_mini_boxes(contour)
            if sside < self.min_size:
                continue
            points = np.array(points)
            if self.score_mode == "fast":
                score = self.box_score_fast(pred, points.reshape(-1, 2))
            else:
                score = self.box_score_slow(pred, contour)
            if self.box_thresh > score:
                continue

            box = self.unclip(points, self.unclip_ratio).reshape(-1, 1, 2)
            box, sside = self.get_mini_boxes(box)
            if sside < self.min_size + 2:
                continue
            box = np.array(box)

            box[:, 0] = np.clip(
                np.round(box[:, 0] / width * dest_width), 0, dest_width)
            box[:, 1] = np.clip(
                np.round(box[:, 1] / height * dest_height), 0, dest_height)
            boxes.append(box.astype("int32"))
            scores.append(score)
        return np.array(boxes, dtype="int32"), scores

    def unclip(self, box, unclip_ratio):
        poly = Polygon(box)
        distance = poly.area * unclip_ratio / poly.length
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(box, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = np.array(offset.Execute(distance))
        return expanded

    def get_mini_boxes(self, contour):
        bounding_box = cv2.minAreaRect(contour)
        points = sorted(list(cv2.boxPoints(bounding_box)), key=lambda x: x[0])

        index_1, index_2, index_3, index_4 = 0, 1, 2, 3
        if points[1][1] > points[0][1]:
            index_1 = 0
            index_4 = 1
        else:
            index_1 = 1
            index_4 = 0
        if points[3][1] > points[2][1]:
            index_2 = 2
            index_3 = 3
        else:
            index_2 = 3
            index_3 = 2

        box = [
            points[index_1], points[index_2], points[index_3], points[index_4]
        ]
        return box, min(bounding_box[1])

    def box_score_fast(self, bitmap, _box):
        """
        box_score_fast: use bbox mean score as the mean score
        """
        h, w = bitmap.shape[:2]
        box = _box.copy()
        xmin = np.clip(np.floor(box[:, 0].min()).astype("int32"), 0, w - 1)
        xmax = np.clip(np.ceil(box[:, 0].max()).astype("int32"), 0, w - 1)
        ymin = np.clip(np.floor(box[:, 1].min()).astype("int32"), 0, h - 1)
        ymax = np.clip(np.ceil(box[:, 1].max()).astype("int32"), 0, h - 1)

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        box[:, 0] = box[:, 0] - xmin
        box[:, 1] = box[:, 1] - ymin
        cv2.fillPoly(mask, box.reshape(1, -1, 2).astype("int32"), 1)
        return cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1], mask)[0]

    def box_score_slow(self, bitmap, contour):
        '''
        box_score_slow: use polyon mean score as the mean score
        '''
        h, w = bitmap.shape[:2]
        contour = contour.copy()
        contour = np.reshape(contour, (-1, 2))

        xmin = np.clip(np.min(contour[:, 0]), 0, w - 1)
        xmax = np.clip(np.max(contour[:, 0]), 0, w - 1)
        ymin = np.clip(np.min(contour[:, 1]), 0, h - 1)
        ymax = np.clip(np.max(contour[:, 1]), 0, h - 1)

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)

        contour[:, 0] = contour[:, 0] - xmin
        contour[:, 1] = contour[:, 1] - ymin

        cv2.fillPoly(mask, contour.reshape(1, -1, 2).astype("int32"), 1)
        return cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1], mask)[0]

    def detect_missing_text_lines(self, pred, boxes):
        """检测可能的缺失文本行"""
        h, w = pred.shape[:2]
        
        # 创建已识别区域的掩码
        detected_mask = np.zeros((h, w), dtype=np.uint8)
        for box in boxes:
            cv2.fillPoly(detected_mask, [np.array(box, dtype=np.int32)], 1)
        
        # 计算未识别区域
        missing_mask = (detected_mask == 0).astype(np.uint8)
        
        # 查找未识别区域的轮廓
        contours, _ = cv2.findContours(missing_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        missing_boxes = []
        for contour in contours:
            if cv2.contourArea(contour) < self.min_size:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            missing_boxes.append([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
        
        return missing_boxes

    def polygons_from_bitmap(self, pred, _bitmap, dest_width, dest_height):
        # 保存bitmap用于调试
        self.bitmap = _bitmap

        bitmap = _bitmap
        height, width = bitmap.shape

        boxes = []
        scores = []
        filtered_by = {'score': 0, 'size': 0, 'unclip': 0}

        contours, _ = cv2.findContours((bitmap * 255).astype(np.uint8),
                                       cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        # 添加调试信息
        if hasattr(self, 'debugger') and self.debugger:
            self.debugger.add_text("轮廓信息", f"检测到 {len(contours)} 个轮廓")

        for contour in contours[:self.max_candidates]:

            score = self.box_score_fast(pred, points.reshape(-1, 2))
            if self.box_thresh > score:
                filtered_by['score'] += 1
                continue
            
            # 其他过滤条件...
            if sside < self.min_size + 2:
                filtered_by['size'] += 1
                continue
            
            # 添加框和分数
            boxes.append(box)
            scores.append(score)

        # 添加过滤统计
        if hasattr(self, 'debugger') and self.debugger:
            filter_info = f"原始轮廓: {len(contours)}\n"
            filter_info += f"过滤掉的轮廓:\n"
            filter_info += f"- 分数过低: {filtered_by['score']}\n"
            filter_info += f"- 尺寸过小: {filtered_by['size']}\n"
            filter_info += f"- Unclip错误: {filtered_by['unclip']}\n"
            filter_info += f"最终保留: {len(boxes)}"
            self.debugger.add_text("过滤统计", filter_info)

        return boxes, scores   

    def assess_polygon_quality(self, polygon):
        try:
            # 计算多边形面积与周长比
            area = cv2.contourArea(polygon.astype(np.float32))
            perimeter = cv2.arcLength(polygon.astype(np.float32), True)

            if perimeter == 0:
                return 0

            # 计算圆度 (4π*面积/周长²)，圆的圆度为1，越接近1质量越高
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # 计算长宽比
            rect = cv2.minAreaRect(polygon.astype(np.float32))
            width, height = rect[1]
            if min(width, height) == 0:
                aspect_ratio = 0
            else:
                aspect_ratio = min(width/max(height, 1e-5), height/max(width, 1e-5))

            # 综合评分
            quality_score = (circularity * 0.7 + aspect_ratio * 0.3)
            return min(max(quality_score, 0), 1)  # 限制在0-1范围内
        except:
            return 0

    def merge_adjacent_text_lines(self, boxes, scores, y_threshold=10, overlap_threshold=0.5):
        """
        合并可能属于同一文本行的相邻框
        
        Args:
            boxes: 检测到的文本框列表
            scores: 对应的得分列表
            y_threshold: Y轴方向上判定为同行的最大差值
            overlap_threshold: 判断为重叠的IOU阈值
        
        Returns:
            合并后的框和得分
        """
        if len(boxes) <= 1:
            return boxes, scores
        
        # 按照y坐标(上边缘)排序
        boxes_with_scores = [(box, score) for box, score in zip(boxes, scores)]
        boxes_with_scores.sort(key=lambda x: np.mean(x[0][:, 1]))
        
        merged_boxes = []
        merged_scores = []
        
        # 当前行的框
        current_line = [boxes_with_scores[0]]
        
        # 遍历所有框
        for i in range(1, len(boxes_with_scores)):
            box, score = boxes_with_scores[i]
            prev_box = current_line[-1][0]
            
            # 计算当前框与前一框的Y轴差值
            curr_y = np.mean(box[:, 1])
            prev_y = np.mean(prev_box[:, 1])
            y_diff = abs(curr_y - prev_y)
            
            if y_diff < y_threshold:
                # 属于同一行，添加到当前行
                current_line.append((box, score))
            else:
                # 新的一行，处理当前行
                if len(current_line) == 1:
                    merged_boxes.append(current_line[0][0])
                    merged_scores.append(current_line[0][1])
                else:
                    # 对当前行按X坐标排序
                    current_line.sort(key=lambda x: np.min(x[0][:, 0]))
                    # 检测重叠
                    final_boxes = []
                    final_scores = []
                    
                    for box_info in current_line:
                        if not final_boxes or not self._has_overlap(box_info[0], final_boxes[-1], overlap_threshold):
                            final_boxes.append(box_info[0])
                            final_scores.append(box_info[1])
                        else:
                            # 合并重叠框
                            merged_box = self._merge_boxes(final_boxes[-1], box_info[0])
                            final_boxes[-1] = merged_box
                            final_scores[-1] = max(final_scores[-1], box_info[1])
                    
                    merged_boxes.extend(final_boxes)
                    merged_scores.extend(final_scores)
                    
                # 开始新的一行
                current_line = [(box, score)]
        
        # 处理最后一行
        if len(current_line) == 1:
            merged_boxes.append(current_line[0][0])
            merged_scores.append(current_line[0][1])
        else:
            current_line.sort(key=lambda x: np.min(x[0][:, 0]))
            final_boxes = []
            final_scores = []
            
            for box_info in current_line:
                if not final_boxes or not self._has_overlap(box_info[0], final_boxes[-1], overlap_threshold):
                    final_boxes.append(box_info[0])
                    final_scores.append(box_info[1])
                else:
                    merged_box = self._merge_boxes(final_boxes[-1], box_info[0])
                    final_boxes[-1] = merged_box
                    final_scores[-1] = max(final_scores[-1], box_info[1])
            
            merged_boxes.extend(final_boxes)
            merged_scores.extend(final_scores)
        
        return merged_boxes, merged_scores

    def _has_overlap(self, box1, box2, threshold=0.5):
        """判断两个框是否有足够的重叠"""
        # 简单判断：检查横向重叠
        x1_min, x1_max = np.min(box1[:, 0]), np.max(box1[:, 0])
        x2_min, x2_max = np.min(box2[:, 0]), np.max(box2[:, 0])
        
        # 计算重叠部分
        overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
        if overlap <= 0:
            return False
        
        # 计算重叠比例
        width1 = x1_max - x1_min
        width2 = x2_max - x2_min
        overlap_ratio = overlap / min(width1, width2)
        
        return overlap_ratio > threshold

    def _merge_boxes(self, box1, box2):
        """合并两个框"""
        points = np.concatenate([box1, box2], axis=0)
        # 使用凸包算法合并点
        hull = cv2.convexHull(points.astype(np.float32))
        return hull.reshape(-1, 2)

    def __call__(self, outs_dict, shape_list):
        pred = outs_dict['maps']
        # if isinstance(pred, paddle.Tensor):
        #     pred = pred.numpy()
        pred = pred[:, 0, :, :]
        segmentation = pred > self.thresh

        boxes_batch = []
        for batch_index in range(pred.shape[0]):
            src_h, src_w, ratio_h, ratio_w = shape_list[batch_index]
            if self.dilation_kernel is not None:
                mask = cv2.dilate(
                    np.array(segmentation[batch_index]).astype(np.uint8),
                    self.dilation_kernel)
            else:
                mask = segmentation[batch_index]
            if self.box_type == 'poly':
                boxes, scores = self.polygons_from_bitmap(pred[batch_index],
                                                          mask, src_w, src_h)
            elif self.box_type == 'quad':
                boxes, scores = self.boxes_from_bitmap(pred[batch_index], mask,
                                                       src_w, src_h)
            else:
                raise ValueError("box_type can only be one of ['quad', 'poly']")

            boxes_batch.append({'points': boxes})

            # 在__call__方法中的boxes_batch填充后，添加相邻文本合并逻辑
            boxes = boxes_batch[batch_index]['points']
            scores_list = scores  # 假设保存了分数

            # 添加合并近邻文本行的逻辑
            merged_boxes, merged_scores = self.merge_adjacent_text_lines(
                boxes, scores_list, y_threshold=10, overlap_threshold=0.5
            )
            boxes_batch[batch_index]['points'] = merged_boxes

        for batch_index in range(len(boxes_batch)):
            # 在返回结果之前应用合并逻辑
            if hasattr(self, 'merge_adjacent_text_lines'):  # 安全检查
                boxes = boxes_batch[batch_index]['points']
                scores_list = boxes_batch[batch_index].get('scores', [1.0] * len(boxes))
                
                try:
                    merged_boxes, merged_scores = self.merge_adjacent_text_lines(
                        boxes, scores_list, y_threshold=10, overlap_threshold=0.5
                    )
                    boxes_batch[batch_index]['points'] = merged_boxes
                    if 'scores' in boxes_batch[batch_index]:
                        boxes_batch[batch_index]['scores'] = merged_scores
                except Exception as e:
                    print(f"合并文本行时出错: {e}")
        
        return boxes_batch


class DistillationDBPostProcess(object):
    def __init__(self,
                 model_name=["student"],
                 key=None,
                 thresh=0.3,
                 box_thresh=0.6,
                 max_candidates=1000,
                 unclip_ratio=1.5,
                 use_dilation=False,
                 score_mode="fast",
                 box_type='quad',
                 **kwargs):
        self.model_name = model_name
        self.key = key
        self.post_process = DBPostProcess(
            thresh=thresh,
            box_thresh=box_thresh,
            max_candidates=max_candidates,
            unclip_ratio=unclip_ratio,
            use_dilation=use_dilation,
            score_mode=score_mode,
            box_type=box_type)

    def __call__(self, predicts, shape_list):
        results = {}
        for k in self.model_name:
            results[k] = self.post_process(predicts[k], shape_list=shape_list)
        return results
