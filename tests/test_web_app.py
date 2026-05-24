from __future__ import annotations

import unittest

from agent_edge import web_app


class WebAppHelpersTest(unittest.TestCase):
    def test_features_include_file_parse(self) -> None:
        titles = {feature["title"] for feature in web_app._features()}
        self.assertIn("文件解析", titles)
        self.assertIn("文件读取", titles)

    def test_safe_filename_removes_path(self) -> None:
        self.assertEqual(web_app._safe_filename("../危险 文件.pdf"), "危险_文件.pdf")

    def test_normalize_backend_rejects_removed_backends(self) -> None:
        self.assertEqual(web_app._normalize_backend(None), "llama_cpp")
        with self.assertRaises(ValueError):
            web_app._normalize_backend("mock")
        with self.assertRaises(ValueError):
            web_app._normalize_backend("ollama")


if __name__ == "__main__":
    unittest.main()
