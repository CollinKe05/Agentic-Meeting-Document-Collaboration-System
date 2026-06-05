"""系统配置 — 所有路径相对于 syss/ 目录"""
import os
from dataclasses import dataclass
from pathlib import Path

_HOME = Path(__file__).resolve().parent  # syss/


@dataclass
class SystemConfig:
    # ── 模型路径 ──
    yolo_model: str = ""
    ocr_model_dir: str = ""
    layoutreader_model: str = ""
    char_dict: str = ""
    # BPU 模型 (RDK X5)
    bpu_runtime_dir: str = ""
    bpu_det_model: str = ""
    bpu_rec_model: str = ""
    bpu_dict: str = ""

    # ── 阈值 ──
    layout_conf: float = 0.2
    layout_iou: float = 0.5
    ocr_rec_thresh: float = 0.5
    block_score_filter: float = 0.5
    dpi: int = 200

    # ── LLM ──
    ollama_model: str = "qwen2.5:1.5b"

    # ── I/O ──
    keep_temp: bool = False
    debug: bool = False
    labels: str = "cn"

    def __post_init__(self):
        m = _HOME / "models"

        # 环境变量可覆盖所有路径
        if not self.yolo_model:
            self.yolo_model = os.environ.get("SYSS_YOLO_MODEL", "")
        if not self.yolo_model:
            p = m / "doclayout_yolo_docstructbench_imgsz1024.onnx"
            if p.exists():
                self.yolo_model = str(p)

        if not self.ocr_model_dir:
            self.ocr_model_dir = os.environ.get("SYSS_OCR_MODEL_DIR", "")
        if not self.ocr_model_dir:
            p = m / "ppocrv4"
            if p.exists():
                self.ocr_model_dir = str(p)

        if not self.char_dict:
            self.char_dict = os.environ.get("SYSS_CHAR_DICT", "")
        if not self.char_dict:
            p = m / "ppocrv4" / "ppocr_keys_v1.txt"
            if p.exists():
                self.char_dict = str(p)

        if not self.layoutreader_model:
            self.layoutreader_model = os.environ.get("SYSS_LAYOUTREADER", "")
        if not self.layoutreader_model:
            p = m / "layoutreader"
            if p.exists():
                self.layoutreader_model = str(p)

        if not self.bpu_runtime_dir:
            self.bpu_runtime_dir = os.environ.get("SYSS_BPU_RUNTIME_DIR", "")
        if not self.bpu_runtime_dir:
            p = Path("/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/runtime/python")
            if p.exists():
                self.bpu_runtime_dir = str(p)

        if not self.bpu_det_model:
            self.bpu_det_model = os.environ.get("SYSS_BPU_DET", "")
        if not self.bpu_det_model:
            p = Path("/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/model/en_PP-OCRv3_det_640x640_nv12.bin")
            if p.exists():
                self.bpu_det_model = str(p)
        if not self.bpu_det_model:
            p = m / "en_PP-OCRv3_det_640x640_nv12.bin"
            if p.exists():
                self.bpu_det_model = str(p)

        if not self.bpu_rec_model:
            self.bpu_rec_model = os.environ.get("SYSS_BPU_REC", "")
        if not self.bpu_rec_model:
            p = Path("/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/model/rec_ppocr_cn.bin")
            if p.exists():
                self.bpu_rec_model = str(p)
        if not self.bpu_rec_model:
            p = m / "rec_ppocr_cn.bin"
            if p.exists():
                self.bpu_rec_model = str(p)
        if not self.bpu_rec_model:
            p = Path("/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/model/en_PP-OCRv3_rec_48x320_rgb.bin")
            if p.exists():
                self.bpu_rec_model = str(p)
        if not self.bpu_rec_model:
            p = m / "en_PP-OCRv3_rec_48x320_rgb.bin"
            if p.exists():
                self.bpu_rec_model = str(p)

        if not self.bpu_dict:
            self.bpu_dict = os.environ.get("SYSS_BPU_DICT", "")
        if not self.bpu_dict:
            p = Path("/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/runtime/python/dict.txt")
            if p.exists():
                self.bpu_dict = str(p)
        if not self.bpu_dict and self.char_dict:
            self.bpu_dict = self.char_dict
