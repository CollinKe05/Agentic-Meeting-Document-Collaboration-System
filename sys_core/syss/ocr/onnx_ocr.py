"""ONNX OCR (CPU 回退) — 封装 ONNXPaddleOcr"""
import os
import sys
from pathlib import Path
import numpy as np

from .base import BaseOCR, PageOCRResult, OCRResult

# 使用 syss 内部的 ppocr 模块
_PPOCR_INNER = Path(__file__).resolve().parent / "ppocr"
if str(_PPOCR_INNER) not in sys.path:
    sys.path.insert(0, str(_PPOCR_INNER))
# 同时加 parent，因为 ppocr 内部有 from ppocr.xxx 的导入路径
_PPOCR_PARENT = _PPOCR_INNER.parent  # syss/ocr/
if str(_PPOCR_PARENT) not in sys.path:
    sys.path.insert(0, str(_PPOCR_PARENT))


class ONNXOCR(BaseOCR):
    def __init__(self, model_dir: str, char_dict: str, rec_thresh: float = 0.5):
        from ppocr.paddleocr import ONNXPaddleOcr

        kwargs = {"use_angle_cls": True, "use_gpu": False, "drop_score": rec_thresh}
        if model_dir:
            kwargs["det_model_dir"] = str(Path(model_dir) / "det" / "ppocr_det.onnx")
            kwargs["rec_model_dir"] = str(Path(model_dir) / "rec" / "ppocr_rec.onnx")
            cls_path = Path(model_dir) / "cls" / "cls.onnx"
            if cls_path.exists():
                kwargs["cls_model_dir"] = str(cls_path)
        if char_dict and Path(char_dict).exists():
            kwargs["rec_char_dict_path"] = str(char_dict)

        self.rec_thresh = rec_thresh
        self.model = ONNXPaddleOcr(**kwargs)

    def process_image(self, image: np.ndarray, page_idx: int = 0) -> PageOCRResult:
        # ppocr 内部使用相对路径写 param/output_full.md
        _PPOCR_INNER.joinpath("param").mkdir(parents=True, exist_ok=True)
        _cwd = os.getcwd()
        try:
            os.chdir(str(_PPOCR_INNER))
            results = self.model.ocr(image, det=True, rec=True, cls=True)
        finally:
            os.chdir(_cwd)
        if not results or not results[0]:
            return PageOCRResult(page_idx=page_idx)
        ocr_list = []
        for line in results[0]:
            pts = line[0]
            text, score = line[1]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            ocr_list.append(OCRResult(
                bbox=[int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                transcription=text, score=float(score),
                illegibility=score < self.rec_thresh))
        return PageOCRResult(page_idx=page_idx, results=ocr_list)
