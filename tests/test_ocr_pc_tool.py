from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import ocr_pc_tool
from agent_edge.heavy_runtime import ManagedProcessResult


class OcrPcToolTest(unittest.TestCase):
    def test_parse_document_returns_runner_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            upload_dir = workspace / "uploads"
            upload_dir.mkdir()
            (upload_dir / "demo.pdf").write_bytes(b"%PDF-test")

            def fake_run(*args, **kwargs):
                self.assertEqual(args[0][0], "custom-python")
                output_root = workspace / "ocr_outputs"
                output_root.mkdir(exist_ok=True)
                (output_root / "demo.md").write_text("完整 OCR 原文", encoding="utf-8")
                result_path = output_root / "demo_ocr_result.json"
                result_path.write_text(
                    json.dumps(
                        {
                            "ok": True,
                            "markdown_path": str(output_root / "demo.md"),
                            "blocks_json_path": str(output_root / "demo_blocks.json"),
                            "content_list_v2_path": str(output_root / "demo_content_list_v2.json"),
                            "images_dir": str(output_root / "demo_pages"),
                            "markdown_preview": "hello",
                        }
                    ),
                    encoding="utf-8",
                )
                return ManagedProcessResult(command=("ocr",), returncode=0, log_path=output_root / "ocr.log", log_tail="ok")

            with mock.patch("agent_edge.ocr_pc_tool.WORKSPACE_DIR", workspace):
                with mock.patch("agent_edge.ocr_pc_tool.create_resource_token", return_value="token"):
                    with mock.patch("agent_edge.ocr_pc_tool.run_ocr_blocking", side_effect=fake_run) as run_mock:
                        with mock.patch.dict("os.environ", {"OCR_PC_PYTHON": "custom-python"}):
                            result = ocr_pc_tool.parse_document_with_ocr_pc({"path": "uploads/demo.pdf"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "ocr_pc")
        self.assertEqual(result["markdown_preview"], "hello")
        self.assertEqual(result["ocr_text"], "完整 OCR 原文")
        self.assertEqual(result["ocr_text_path"], str(Path(result["markdown_path"])))
        run_mock.assert_called_once()

    def test_rejects_unsupported_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "demo.txt").write_text("hello", encoding="utf-8")
            with mock.patch("agent_edge.ocr_pc_tool.WORKSPACE_DIR", workspace):
                with self.assertRaises(ValueError):
                    ocr_pc_tool.parse_document_with_ocr_pc({"path": "demo.txt"})


if __name__ == "__main__":
    unittest.main()
