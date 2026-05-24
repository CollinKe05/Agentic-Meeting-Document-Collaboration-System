from __future__ import annotations

import unittest

try:
    from agent_edge.graph import _build_summary, _normalize_plan, _should_direct_chat, run_agent
except ModuleNotFoundError as exc:  # Windows host may not have LangGraph deps installed.
    _build_summary = None
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

    def test_markdown_file_uses_safe_text_reader_even_if_planned_as_mineru(self) -> None:
        plan = [
            {"id": 1, "kind": "learn_skill", "skill_file": "local_tool_skill.md"},
            {
                "id": 2,
                "kind": "use_tool",
                "tool_name": "PARSE_DOCUMENT_WITH_MINERU",
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

    def test_pdf_file_uses_mineru_even_if_planned_as_text_reader(self) -> None:
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

        self.assertEqual(normalized[1]["tool_name"], "PARSE_DOCUMENT_WITH_MINERU")
        self.assertEqual(normalized[1]["tool_input"], {"path": "uploads/report.pdf"})


if __name__ == "__main__":
    unittest.main()
