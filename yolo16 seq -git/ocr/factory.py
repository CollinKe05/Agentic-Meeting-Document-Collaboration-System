"""OCR 工厂 — 自动检测 BPU vs ONNX"""
from ..config import SystemConfig
from .base import BaseOCR


def create_ocr(config: SystemConfig) -> BaseOCR:
    bpu = _is_bpu_available()
    if bpu and config.bpu_det_model and config.bpu_rec_model:
        print("[OCR] BPU (RDK X5) 已检测，使用硬件加速")
        from .bpu_ocr import BPUOCR
        return BPUOCR(
            det_model=config.bpu_det_model,
            rec_model=config.bpu_rec_model,
            char_dict=config.char_dict,
            rec_thresh=config.ocr_rec_thresh)
    else:
        if not bpu:
            print("[OCR] BPU 不可用，回退到 ONNX (CPU)")
        else:
            print("[OCR] BPU 模型文件缺失，回退到 ONNX (CPU)")
        from .onnx_ocr import ONNXOCR
        return ONNXOCR(
            model_dir=config.ocr_model_dir,
            char_dict=config.char_dict,
            rec_thresh=config.ocr_rec_thresh)


def _is_bpu_available() -> bool:
    try:
        import hbm_runtime  # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False
