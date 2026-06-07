"""中文路径兼容的图像读写"""
from pathlib import Path
import cv2
import numpy as np


def imread_cn(path: str) -> np.ndarray:
    with open(path, "rb") as f:
        data = np.frombuffer(f.read(), np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_cn(path: str, img: np.ndarray):
    ext = Path(path).suffix
    _, buf = cv2.imencode(ext, img)
    with open(path, "wb") as f:
        f.write(buf)
