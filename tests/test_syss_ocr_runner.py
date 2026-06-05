from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import syss_ocr_runner


class SyssOcrRunnerTest(unittest.TestCase):
    def test_runner_requests_resource_then_writes_compatible_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "demo.png"
            output_root = root / "out"
            input_path.write_bytes(b"image")

            fake_config_module = types.ModuleType("sys_core.syss.config")
            fake_pipeline_module = types.ModuleType("sys_core.syss.pipeline")

            class FakeConfig:
                pass

            class FakePipeline:
                def __init__(self, config):
                    self.config = config

                def run(self, source, output_dir):
                    out = Path(output_dir)
                    markdown = out / "demo.md"
                    merged = out / "demo_merged.json"
                    sorted_json = out / "demo_sorted.json"
                    markdown.write_text("# 文档内容\n\n中文 OCR\n", encoding="utf-8")
                    merged.write_text("{}", encoding="utf-8")
                    sorted_json.write_text(
                        json.dumps(
                            {
                                "pages": [
                                    {
                                        "page_index": 0,
                                        "blocks": [
                                            {
                                                "block_info": {
                                                    "class_name": "正文",
                                                    "bbox": [1, 2, 30, 40],
                                                    "textbox_reading_order_median": 0,
                                                },
                                                "contained_text_boxes": [
                                                    {"transcription": "中文", "is_virtual": False},
                                                    {"transcription": "", "is_virtual": True},
                                                ],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ),
                        encoding="utf-8",
                    )
                    return {
                        "markdown": str(markdown),
                        "merged_json": str(merged),
                        "sorted_json": str(sorted_json),
                        "images_dir": None,
                        "block_count": 1,
                        "text_count": 1,
                        "pages": 1,
                        "elapsed": 0.1,
                        "ocr_backend": "RDKBPUOCR",
                        "layout_backend": "LayoutAnalyzer",
                        "sorter_backend": "FastReadingOrderSorter",
                    }

            fake_config_module.SystemConfig = FakeConfig
            fake_pipeline_module.DocumentPipeline = FakePipeline

            with mock.patch.dict(
                sys.modules,
                {
                    "sys_core.syss.config": fake_config_module,
                    "sys_core.syss.pipeline": fake_pipeline_module,
                },
            ):
                with mock.patch("agent_edge.syss_ocr_runner._post_json", return_value={"ok": True}) as post_mock:
                    rc = syss_ocr_runner.main(
                        [
                            "--input",
                            str(input_path),
                            "--output-root",
                            str(output_root),
                            "--task-id",
                            "task123",
                            "--token",
                            "token",
                            "--callback-url",
                            "http://127.0.0.1:7860/api/runtime/resource",
                        ]
                    )

            result = json.loads((output_root / "demo_ocr_result.json").read_text(encoding="utf-8"))
            content_v2 = json.loads(Path(result["content_list_v2_path"]).read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(post_mock.call_args_list[0].args[0], "http://127.0.0.1:7860/api/runtime/resource/request")
        self.assertEqual(post_mock.call_args_list[1].args[0], "http://127.0.0.1:7860/api/runtime/resource/release")
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "syss")
        self.assertEqual(result["ocr_backend"], "rdk_bpu")
        self.assertEqual(result["block_count"], 1)
        self.assertEqual(result["markdown_preview"], "# 文档内容\n\n中文 OCR\n")
        self.assertEqual(content_v2[0]["text"], "中文")

    def test_runner_can_load_external_syss_project_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "syss_f16yolo"
            project_dir.mkdir()
            (project_dir / "__init__.py").write_text("", encoding="utf-8")
            (project_dir / "config.py").write_text(
                """
class SystemConfig:
    def __init__(self):
        self.name = "external"
""",
                encoding="utf-8",
            )
            (project_dir / "pipeline.py").write_text(
                """
import json
from pathlib import Path

from .config import SystemConfig

class DocumentPipeline:
    def __init__(self, config: SystemConfig):
        self.config = config

    def run(self, source, output_dir):
        out = Path(output_dir)
        markdown = out / "demo.md"
        merged = out / "demo_merged.json"
        sorted_json = out / "demo_sorted.json"
        markdown.write_text("external syss markdown", encoding="utf-8")
        merged.write_text("{}", encoding="utf-8")
        sorted_json.write_text(json.dumps({"pages": []}), encoding="utf-8")
        return {
            "markdown": str(markdown),
            "merged_json": str(merged),
            "sorted_json": str(sorted_json),
            "block_count": 0,
            "pages": 1,
            "ocr_backend": "RDKBPUOCR",
        }
""",
                encoding="utf-8",
            )
            input_path = root / "demo.png"
            output_root = root / "out"
            input_path.write_bytes(b"image")

            for name in ["syss_f16yolo", "syss_f16yolo.config", "syss_f16yolo.pipeline"]:
                sys.modules.pop(name, None)

            with mock.patch.dict("os.environ", {"SYSS_PROJECT_DIR": str(project_dir)}):
                with mock.patch("agent_edge.syss_ocr_runner._post_json", return_value={"ok": True}):
                    rc = syss_ocr_runner.main(
                        [
                            "--input",
                            str(input_path),
                            "--output-root",
                            str(output_root),
                            "--task-id",
                            "task456",
                            "--token",
                            "token",
                            "--callback-url",
                            "http://127.0.0.1:7860/api/runtime/resource",
                        ]
                    )

            result = json.loads((output_root / "demo_ocr_result.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(result["syss_import"], "syss_f16yolo")
        self.assertEqual(result["syss_project_dir"], str(project_dir))
        self.assertEqual(result["markdown_preview"], "external syss markdown")


if __name__ == "__main__":
    unittest.main()
