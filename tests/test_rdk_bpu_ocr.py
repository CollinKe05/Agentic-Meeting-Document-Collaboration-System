from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sys_core.syss.ocr.rdk_bpu_ocr import RDKBPUOCR


class RDKBPUOCRTest(unittest.TestCase):
    def test_predict_results_are_mapped_to_page_ocr_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "rdk_model_zoo" / "samples" / "vision" / "PaddleOCR" / "runtime" / "python"
            model_dir = root / "rdk_model_zoo" / "samples" / "vision" / "PaddleOCR" / "model"
            runtime_dir.mkdir(parents=True)
            model_dir.mkdir(parents=True)
            det_model = model_dir / "en_PP-OCRv3_det_640x640_nv12.bin"
            rec_model = model_dir / "rec_ppocr_cn.bin"
            dict_path = runtime_dir / "dict.txt"
            det_model.write_bytes(b"det")
            rec_model.write_bytes(b"rec")
            dict_path.write_text("中\n文\n", encoding="utf-8")
            (runtime_dir / "paddleocr.py").write_text(
                """
class PaddleOCRConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

class PaddleOCR:
    def __init__(self, config):
        self.config = config
        self.scheduling = None

    def set_scheduling_params(self, priority=None, bpu_cores=None):
        self.scheduling = (priority, bpu_cores)

    def predict(self, image):
        return [
            [[1, 2], [9, 2], [9, 7], [1, 7]],
            [[10, 12], [20, 12], [20, 16], [10, 16]],
        ], ["中文", "OCR"]
""",
                encoding="utf-8",
            )

            ocr = RDKBPUOCR(
                runtime_dir=str(runtime_dir),
                det_model=str(det_model),
                rec_model=str(rec_model),
                dict_path=str(dict_path),
            )
            result = ocr.process_image(object(), page_idx=3)

        self.assertEqual(result.page_idx, 3)
        self.assertEqual(len(result.results), 2)
        self.assertEqual(result.results[0].bbox, [1, 2, 9, 7])
        self.assertEqual(result.results[0].transcription, "中文")
        self.assertEqual(result.results[1].bbox, [10, 12, 20, 16])
        self.assertEqual(result.results[1].score, 1.0)


if __name__ == "__main__":
    unittest.main()
