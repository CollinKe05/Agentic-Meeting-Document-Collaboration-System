"""PDF → 图片转换"""
from typing import List
import fitz
import numpy as np
import cv2


def pdf_to_images(pdf_path: str, dpi: int = 200, page_range: tuple = None) -> List[np.ndarray]:
    """将PDF每页渲染为BGR格式的numpy数组"""
    doc = fitz.open(pdf_path)
    total = len(doc)

    start, end = 0, total
    if page_range:
        start = max(0, page_range[0])
        end = min(total, page_range[1])

    images = []
    for i in range(start, end):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        images.append(img)

    doc.close()
    return images
