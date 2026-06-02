# 中文 PaddleOCR 推理入口 (基于官方 main.py 修改, 增加 --dict-path)
from __future__ import annotations
import argparse
import logging
import os
import sys

import cv2
import numpy as np

sys.path.append(os.path.abspath("../../../../../"))
from paddleocr import PaddleOCR, PaddleOCRConfig

logging.basicConfig(level=logging.INFO,
                    format="[%(name)s] [%(asctime)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("PaddleOCR")


def main() -> None:
    p = argparse.ArgumentParser(description="中文 PaddleOCR BPU 推理")
    p.add_argument("--det-model-path", required=True, help="检测 .bin (官方 en_PP-OCRv3_det nv12)")
    p.add_argument("--rec-model-path", required=True, help="识别 .bin (中文 rec_ppocr_cn int16)")
    p.add_argument("--dict-path", default="./dict.txt", help="中文字典 dict.txt")
    p.add_argument("--test-img", required=True, help="输入图片")
    p.add_argument("--det-threshold", type=float, default=0.5)
    p.add_argument("--img-save-path", default="./result.jpg")
    p.add_argument("--priority", type=int, default=0)
    p.add_argument("--bpu-cores", nargs="+", type=int, default=[0])
    args = p.parse_args()

    config = PaddleOCRConfig(
        det_model_path=args.det_model_path,
        rec_model_path=args.rec_model_path,
        dict_path=args.dict_path,
        det_threshold=args.det_threshold,
    )
    model = PaddleOCR(config)
    model.set_scheduling_params(priority=args.priority, bpu_cores=args.bpu_cores)

    image = cv2.imread(args.test_img)
    if image is None:
        raise FileNotFoundError(f"无法读取图片: {args.test_img}")

    boxes, texts = model.predict(image)

    logger.info(f"检测到 {len(boxes)} 个文本区域:")
    for i, (box, text) in enumerate(zip(boxes, texts), start=1):
        logger.info(f"  [{i}] {text}")

    # 可视化: 画检测框 (中文写图会乱码, 故只画框, 文字看终端)
    vis = image.copy()
    for box in boxes:
        cv2.polylines(vis, [box.astype(int)], isClosed=True, color=(0, 255, 0), thickness=2)
    cv2.imwrite(args.img_save_path, vis)
    logger.info(f"框可视化已保存: {args.img_save_path}")


if __name__ == "__main__":
    main()
