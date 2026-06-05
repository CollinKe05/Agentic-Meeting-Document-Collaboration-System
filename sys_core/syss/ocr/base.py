"""OCR 基类接口"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING, List

if TYPE_CHECKING:
    import numpy as np
else:
    np = Any


@dataclass
class OCRResult:
    bbox: list            # [x1, y1, x2, y2]
    transcription: str
    score: float
    illegibility: bool = False

@dataclass
class PageOCRResult:
    page_idx: int
    results: List[OCRResult] = field(default_factory=list)


class BaseOCR(ABC):
    @abstractmethod
    def process_image(self, image: np.ndarray, page_idx: int = 0) -> PageOCRResult:
        ...

    def process_images(self, images: List[np.ndarray]) -> List[PageOCRResult]:
        return [self.process_image(img, i) for i, img in enumerate(images)]
