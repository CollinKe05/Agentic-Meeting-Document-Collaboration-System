"""OCR 工厂 — 自动检测 BPU vs ONNX"""
from ..config import SystemConfig
from .base import BaseOCR


def create_ocr(config: SystemConfig) -> BaseOCR:
    bpu = _is_bpu_available()
    if bpu and _can_use_rdk_bpu(config):
        print("[OCR] RDK PaddleOCR BPU 已检测，使用板端官方 runtime")
        from .rdk_bpu_ocr import RDKBPUOCR
        return RDKBPUOCR(
            runtime_dir=config.bpu_runtime_dir,
            det_model=config.bpu_det_model,
            rec_model=config.bpu_rec_model,
            dict_path=config.bpu_dict or config.char_dict,
            rec_thresh=config.ocr_rec_thresh)
    if bpu and _exists(config.bpu_det_model) and _exists(config.bpu_rec_model):
        print("[OCR] BPU (RDK X5) 已检测，使用内置硬件加速适配器")
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


def _can_use_rdk_bpu(config: SystemConfig) -> bool:
    return (
        _exists(config.bpu_runtime_dir)
        and _exists(config.bpu_det_model)
        and _exists(config.bpu_rec_model)
        and _exists(config.bpu_dict or config.char_dict)
    )


def _exists(path: str) -> bool:
    from pathlib import Path

    return bool(path) and Path(path).expanduser().exists()
