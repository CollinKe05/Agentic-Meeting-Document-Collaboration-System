from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "agent_edge").is_dir() and (parent / "models").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_project_root()
MODELS_DIR = PROJECT_ROOT / "models"


def _env_path(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return str(Path(value).expanduser()) if value else ""


def _first_existing(*candidates: Path) -> str:
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


@dataclass
class SystemConfig:
    yolo_model: str = ""
    ocr_model_dir: str = ""
    layoutreader_model: str = ""
    char_dict: str = ""
    bpu_det_model: str = ""
    bpu_rec_model: str = ""
    bpu_runtime_dir: str = ""

    layout_conf: float = 0.2
    layout_iou: float = 0.5
    ocr_rec_thresh: float = 0.5
    block_score_filter: float = 0.5
    dpi: int = 300

    keep_temp: bool = False
    debug: bool = False
    labels: str = "cn"

    def __post_init__(self) -> None:
        if not self.yolo_model:
            self.yolo_model = _env_path("SYSS_YOLO_MODEL") or _first_existing(
                MODELS_DIR / "yolov8n_layout_general6.onnx",
                MODELS_DIR / "doclayout_yolo_docstructbench_imgsz1024.onnx",
                MODELS_DIR / "doclayout_yolo_docstructbench_imgsz1024_fp16.onnx",
            )

        if not self.ocr_model_dir:
            self.ocr_model_dir = _env_path("SYSS_OCR_MODEL_DIR") or _first_existing(MODELS_DIR / "ppocrv4")

        if not self.char_dict:
            self.char_dict = (
                _env_path("SYSS_CHAR_DICT")
                or _env_path("SYSS_BPU_DICT")
                or _first_existing(MODELS_DIR / "ppocrv4" / "ppocr_keys_v1.txt", MODELS_DIR / "ppocrv4" / "en_dict.txt")
            )

        if not self.layoutreader_model:
            self.layoutreader_model = _env_path("SYSS_LAYOUTREADER") or _first_existing(MODELS_DIR / "layoutreader")

        if not self.bpu_det_model:
            self.bpu_det_model = _env_path("SYSS_BPU_DET") or _first_existing(MODELS_DIR / "en_PP-OCRv3_det_640x640_nv12.bin")

        if not self.bpu_rec_model:
            self.bpu_rec_model = _env_path("SYSS_BPU_REC") or _first_existing(
                MODELS_DIR / "rec_ppocr_cn.bin",
                MODELS_DIR / "en_PP-OCRv3_rec_48x320_rgb.bin",
            )

        if not self.bpu_runtime_dir:
            self.bpu_runtime_dir = _env_path("SYSS_BPU_RUNTIME_DIR")
