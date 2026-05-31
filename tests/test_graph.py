from __future__ import annotations

import unittest

try:
    from agent_edge.graph import _build_summary, _deterministic_plan, _normalize_plan, _should_direct_chat, run_agent
except ModuleNotFoundError as exc:  # Windows host may not have LangGraph deps installed.
    _build_summary = None
    _deterministic_plan = None
    _normalize_plan = None
    _should_direct_chat = None
    run_agent = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@unittest.skipIf(_normalize_plan is None, f"graph dependencies unavailable: {_IMPORT_ERROR}")
class GraphToolRoutingTest(unittest.TestCase):
    def test_plain_greeting_uses_direct_chat_without_tools(self) -> None:
        self.assertTrue(_should_direct_chat("你好"))

        from unittest import mock

        with mock.patch("agent_edge.graph.llm_call", return_value="你好，我在。"):
            state = run_agent("你好")

        self.assertEqual(state["current_response"], "你好，我在。")
        self.assertEqual(state["plan"], [])
        self.assertEqual(state["past_steps"], [])

    def test_direct_chat_receives_conversation_context(self) -> None:
        from unittest import mock

        with mock.patch("agent_edge.graph.llm_call", return_value="继续聊。") as llm_mock:
            state = run_agent("接着说", conversation_context="User: 上一轮\nAssistant: 上一轮回答")

        self.assertEqual(state["current_response"], "继续聊。")
        self.assertIn("上一轮回答", llm_mock.call_args.args[0])

    def test_file_request_does_not_use_direct_chat(self) -> None:
        self.assertFalse(_should_direct_chat("请读取文件 uploads/readme.md"))

    def test_read_file_summary_uses_llm_for_final_answer(self) -> None:
        past_steps = [
            (
                (
                    "USE_TOOL",
                    '{"tool_name": "SAFE_READ_TEXT_FILE", "args": {"path": "uploads/test.txt"}}',
                ),
                '{"ok": true, "path": "uploads/test.txt", "content": "这是一个测试文档。"}',
            )
        ]

        from unittest import mock

        with mock.patch("agent_edge.graph.llm_call", return_value="我看到你了") as llm_mock:
            summary = _build_summary(past_steps, "请总结这个文档")

        self.assertIn("我看到你了", summary)
        self.assertNotIn("内容为：这是一个测试文档", summary)
        llm_mock.assert_called_once()

    def test_markdown_file_uses_safe_text_reader_even_if_planned_as_ocr(self) -> None:
        plan = [
            {"id": 1, "kind": "learn_skill", "skill_file": "local_tool_skill.md"},
            {
                "id": 2,
                "kind": "use_tool",
                "tool_name": "PARSE_DOCUMENT_WITH_OCR_PC",
                "tool_input": {"path": "uploads/readme.md"},
            },
        ]

        normalized = _normalize_plan(plan, "please read uploads/readme.md")

        self.assertEqual(normalized[1]["tool_name"], "SAFE_READ_TEXT_FILE")
        self.assertEqual(normalized[1]["tool_input"], {"path": "uploads/readme.md"})

    def test_attachment_display_name_resolves_to_uploaded_path(self) -> None:
        plan = [
            {"id": 1, "kind": "learn_skill", "skill_file": "read_file_skill.md"},
            {
                "id": 2,
                "kind": "use_tool",
                "tool_name": "SAFE_READ_TEXT_FILE",
                "tool_input": {"path": "test.txt"},
            },
        ]
        user_input = (
            "你帮我总结一下这个文档\n"
            "<attachments>\n"
            "- test.txt: uploads/6840a4d7cb49-test.txt\n"
            "</attachments>"
        )

        normalized = _normalize_plan(plan, user_input)

        self.assertEqual(normalized[1]["tool_name"], "SAFE_READ_TEXT_FILE")
        self.assertEqual(normalized[1]["tool_input"], {"path": "uploads/6840a4d7cb49-test.txt"})

    def test_chinese_attachment_path_resolves_to_uploaded_path(self) -> None:
        plan = _deterministic_plan(
            "请使用 PARSE_DOCUMENT_WITH_OCR_PC 解析文件 uploads/089470401b35-港科大Introduction_of_CBE_PG_programs.pdf\n"
            "<attachments>\n"
            "- 港科大Introduction_of_CBE_PG_programs.pdf: uploads/089470401b35-港科大Introduction_of_CBE_PG_programs.pdf\n"
            "</attachments>"
        )

        self.assertEqual(plan[1]["tool_name"], "PARSE_DOCUMENT_WITH_OCR_PC")
        self.assertEqual(plan[1]["tool_input"], {"path": "uploads/089470401b35-港科大Introduction_of_CBE_PG_programs.pdf"})

    def test_pdf_file_uses_ocr_even_if_planned_as_text_reader(self) -> None:
        plan = [
            {"id": 1, "kind": "learn_skill", "skill_file": "local_tool_skill.md"},
            {
                "id": 2,
                "kind": "use_tool",
                "tool_name": "SAFE_READ_TEXT_FILE",
                "tool_input": {"path": "uploads/report.pdf"},
            },
        ]

        normalized = _normalize_plan(plan, "please parse uploads/report.pdf")

        self.assertEqual(normalized[1]["tool_name"], "PARSE_DOCUMENT_WITH_OCR_PC")
        self.assertEqual(normalized[1]["tool_input"], {"path": "uploads/report.pdf"})

    def test_explicit_ocr_request_builds_deterministic_plan(self) -> None:
        plan = _deterministic_plan("请使用 PARSE_DOCUMENT_WITH_OCR_PC 解析 uploads/report.pdf")

        self.assertEqual(plan[0]["skill_file"], "ocr_document_skill.md")
        self.assertEqual(plan[1]["tool_name"], "PARSE_DOCUMENT_WITH_OCR_PC")
        self.assertEqual(plan[1]["tool_input"], {"path": "uploads/report.pdf"})

    def test_follow_up_question_uses_latest_ocr_result(self) -> None:
        from unittest import mock

        with mock.patch("agent_edge.graph.latest_ocr_result_exists", return_value=True):
            plan = _deterministic_plan("研究生课程的申请截止日期、奖学金跟我总结一下")

        self.assertEqual(plan[0]["skill_file"], "ocr_document_skill.md")
        self.assertEqual(plan[1]["tool_name"], "READ_LAST_OCR_RESULT")

    def test_last_ocr_result_summary_uses_content(self) -> None:
        past_steps = [
            (
                (
                    "USE_TOOL",
                    '{"tool_name": "READ_LAST_OCR_RESULT", "args": {}}',
                ),
                '{"ok": true, "path": "ocr_outputs/report.md", "content": "Application deadline: June 1. Scholarship deadline: May 1."}',
            )
        ]

        from unittest import mock

        with mock.patch("agent_edge.graph.llm_call", return_value="申请截止日期：6月1日；奖学金截止日期：5月1日。") as llm_mock:
            summary = _build_summary(past_steps, "根据上一次OCR结果回答我")

        self.assertIn("申请截止日期：6月1日", summary)
        llm_mock.assert_called_once()

    def test_ocr_summary_uses_markdown_preview_when_requested(self) -> None:
        past_steps = [
            (
                (
                    "USE_TOOL",
                    '{"tool_name": "PARSE_DOCUMENT_WITH_OCR_PC", "args": {"path": "uploads/report.pdf"}}',
                ),
                (
                    '{"ok": true, "markdown_path": "ocr_outputs/report.md", '
                    '"content_list_v2_path": "ocr_outputs/report_content_list_v2.json", '
                    '"blocks_json_path": "ocr_outputs/report_blocks.json", '
                    '"images_dir": "ocr_outputs/report_pages", '
                    '"ocr_text": "完整 OCR 原文", '
                    '"block_count": 3, "markdown_preview": "项目介绍：化学及生物工程。"}'
                ),
            )
        ]

        from unittest import mock

        with mock.patch("agent_edge.graph.llm_call", return_value="文档主题：项目介绍") as llm_mock:
            summary = _build_summary(past_steps, "请总结这个 PDF")

        self.assertIn("OCR 文档解析完成", summary)
        self.assertIn("完整 OCR 原文", summary)
        self.assertIn("ocr_outputs/report_blocks.json", summary)
        self.assertIn("文档主题：项目介绍", summary)
        llm_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
