"""RDK PaddleOCR BPU adapter.

This wraps the official RDK sample runtime instead of duplicating its model
pre/post-processing. The runtime is expected to live on the board under:
/home/sunrise/rdk_model_zoo/samples/vision/PaddleOCR/runtime/python
"""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

from .base import BaseOCR, OCRResult, PageOCRResult


class RDKBPUOCR(BaseOCR):
    def __init__(
        self,
        *,
        runtime_dir: str,
        det_model: str,
        rec_model: str,
        dict_path: str,
        rec_thresh: float = 0.5,
        det_thresh: float = 0.5,
        priority: int = 0,
        bpu_cores: list[int] | None = None,
    ) -> None:
        self.runtime_dir = _require_path(runtime_dir, "RDK PaddleOCR runtime dir")
        self.det_model = _require_path(det_model, "BPU detection model")
        self.rec_model = _require_path(rec_model, "BPU recognition model")
        self.dict_path = _require_path(dict_path, "BPU OCR dictionary")
        self.rec_thresh = rec_thresh

        module = _load_rdk_paddleocr_module(self.runtime_dir)
        config = module.PaddleOCRConfig(
            det_model_path=str(self.det_model),
            rec_model_path=str(self.rec_model),
            dict_path=str(self.dict_path),
            det_threshold=det_thresh,
        )
        self.model = module.PaddleOCR(config)
        if hasattr(self.model, "set_scheduling_params"):
            self.model.set_scheduling_params(priority=priority, bpu_cores=bpu_cores or [0])

    def process_image(self, image: Any, page_idx: int = 0) -> PageOCRResult:
        boxes, texts = self.model.predict(image)
        results: list[OCRResult] = []
        for box, text in zip(boxes, texts):
            bbox = _polygon_to_bbox(box)
            transcription = str(text or "")
            results.append(
                OCRResult(
                    bbox=bbox,
                    transcription=transcription,
                    score=1.0,
                    illegibility=False,
                )
            )
        return PageOCRResult(page_idx=page_idx, results=results)


def _load_rdk_paddleocr_module(runtime_dir: Path) -> ModuleType:
    source = runtime_dir / "paddleocr.py"
    if not source.exists():
        raise FileNotFoundError(str(source))

    module_name = f"_syss_rdk_paddleocr_{abs(hash(str(source.resolve())))}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load RDK PaddleOCR runtime from {source}")

    module = importlib.util.module_from_spec(spec)
    with _runtime_import_context(runtime_dir):
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
    return module


@contextmanager
def _runtime_import_context(runtime_dir: Path) -> Iterator[None]:
    old_cwd = os.getcwd()
    added: list[str] = []
    candidates = [runtime_dir]
    # Official PaddleOCR sample imports utils.py_utils from the rdk_model_zoo root.
    if len(runtime_dir.parents) >= 5:
        candidates.append(runtime_dir.parents[4])

    try:
        os.chdir(runtime_dir)
        for path in candidates:
            value = str(path)
            if value not in sys.path:
                sys.path.insert(0, value)
                added.append(value)
        yield
    finally:
        os.chdir(old_cwd)
        for value in added:
            try:
                sys.path.remove(value)
            except ValueError:
                pass


def _require_path(path: str, label: str) -> Path:
    p = Path(str(path or "")).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"{label} not found: {p}")
    return p.resolve()


def _polygon_to_bbox(box: Any) -> list[int]:
    points = box.tolist() if hasattr(box, "tolist") else box
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
