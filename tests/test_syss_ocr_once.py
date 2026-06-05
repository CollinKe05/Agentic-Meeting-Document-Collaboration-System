from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import syss_ocr_once


class SyssOcrOnceTest(unittest.TestCase):
    def test_once_cli_writes_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "demo.pdf"
            output_root = root / "out"
            input_path.write_bytes(b"%PDF-test")

            expected = {
                "ok": True,
                "backend": "syss",
                "markdown_path": str(output_root / "demo.md"),
            }
            with mock.patch.dict("os.environ", {}, clear=True):
                with mock.patch("agent_edge.syss_ocr_once.run_syss_ocr", return_value=expected) as run_mock:
                    rc = syss_ocr_once.main(
                        [
                            "--input",
                            str(input_path),
                            "--output-root",
                            str(output_root),
                            "--syss-project-dir",
                            str(root / "syss_f16yolo"),
                        ]
                    )

            result = json.loads((output_root / "demo_ocr_result.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(result, expected)
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
