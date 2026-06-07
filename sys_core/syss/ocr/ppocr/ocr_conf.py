# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：config
# @Date   ：2024/7/31 18:15
# @Author ：leemysw

# 2024/7/31 18:15   Create
# =====================================================

import os
from typing import List

from pydantic import BaseModel, Field

# OCR_MODEL_DIR: str = os.path.join("/data/models/", "ppocr/onnx")
OCR_MODEL_DIR: str = os.path.join("model/")


class OCRConfig(BaseModel):
    # params for prediction engine
    use_gpu: bool = Field(default=True)
    ir_optim: bool = Field(default=True)
    min_subgraph_size: int = Field(default=15)
    precision: str = Field(default="fp32")
    gpu_mem: int = Field(default=500)
    gpu_id: int = Field(default=0)

    # params for text detector
    page_num: int = Field(default=0)
    det_algorithm: str = Field(default='DB')
    det_model_dir: str = Field(default=os.path.join(OCR_MODEL_DIR, "ppocrv4/det/ppocr_det.onnx"))
    det_limit_side_len: float = Field(default=960)
    det_limit_type: str = Field(default='max')
    det_box_type: str = Field(default='quad')

    # DB params
    det_db_thresh: float = Field(default=0.3)
    det_db_box_thresh: float = Field(default=0.3)
    det_db_unclip_ratio: float = Field(default=1.8)
    # det_db_box_thresh: float = Field(default=0.5)
    # det_db_unclip_ratio: float = Field(default=1.8)

    max_batch_size: int = Field(default=10)
    use_dilation: bool = Field(default=False)
    det_db_score_mode: str = Field(default="fast")

    # EAST params
    det_east_score_thresh: float = Field(default=0.8)
    det_east_cover_thresh: float = Field(default=0.1)
    det_east_nms_thresh: float = Field(default=0.2)

    # SAST params
    det_sast_score_thresh: float = Field(default=0.5)
    det_sast_nms_thresh: float = Field(default=0.2)

    # PSE params
    det_pse_thresh: float = Field(default=0)
    det_pse_box_thresh: float = Field(default=0.85)
    det_pse_min_area: float = Field(default=16)
    det_pse_scale: int = Field(default=1)

    # FCE params
    scales: List[int] = Field(default=[8, 16, 32])
    alpha: float = Field(default=1.0)
    beta: float = Field(default=1.0)
    fourier_degree: int = Field(default=5)

    # params for text recognizer
    rec_algorithm: str = Field(default='SVTR_LCNet')
    rec_model_dir: str = Field(default=os.path.join(OCR_MODEL_DIR, "ppocrv4/rec/ppocr_rec.onnx"))
    rec_image_inverse: bool = Field(default=True)
    rec_image_shape: str = Field(default="3, 48, 320")
    rec_batch_num: int = Field(default=6)
    max_text_length: int = Field(default=25)
    rec_char_dict_path: str = Field(default=os.path.join(OCR_MODEL_DIR, "ppocrv4/ppocr_keys_v1.txt"))
    use_space_char: bool = Field(default=True)
    vis_font_path: str = Field(default="./onnxocr/fonts/simfang.ttf")
    drop_score: float = Field(default=0.5)

    # params for e2e
    e2e_algorithm: str = Field(default='PGNet')
    e2e_model_dir: str = ""
    e2e_limit_side_len: float = Field(default=768)
    e2e_limit_type: str = Field(default='max')

    # PGNet params
    e2e_pgnet_score_thresh: float = Field(default=0.5)
    e2e_char_dict_path: str = Field(default="./onnxocr/ppocr/utils/ic15_dict.txt")
    e2e_pgnet_valid_set: str = Field(default='totaltext')
    e2e_pgnet_mode: str = Field(default='fast')

    # params for text classifier
    use_angle_cls: bool = Field(default=True)
    cls_model_dir: str = Field(default=os.path.join(OCR_MODEL_DIR, "ppocrv4/cls/cls.onnx"))
    cls_image_shape: str = Field(default="3, 48, 192")
    label_list: List[str] = Field(default=['0', '180'])
    cls_batch_num: int = Field(default=6)
    cls_thresh: float = Field(default=0.9)

    enable_mkldnn: bool = Field(default=False)
    cpu_threads: int = Field(default=10)
    use_pdserving: bool = Field(default=False)
    warmup: bool = Field(default=False)

    # SR params
    sr_model_dir: str = ""
    sr_image_shape: str = Field(default="3, 32, 128")
    sr_batch_num: int = Field(default=1)

    draw_img_save_dir: str = Field(default="./onnxocr/inference_results")
    save_crop_res: bool = Field(default=False)
    crop_res_save_dir: str = Field(default="./onnxocr/output")

    # multi-process
    use_mp: bool = Field(default=False)
    total_process_num: int = Field(default=1)
    process_id: int = Field(default=0)

    benchmark: bool = Field(default=False)
    show_log: bool = Field(default=True)
    use_onnx: bool = Field(default=False)
