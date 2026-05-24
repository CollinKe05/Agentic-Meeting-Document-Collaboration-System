from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import event_agent, task_store


class EventAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "tasks.sqlite3"
        self.env = mock.patch.dict(os.environ, {"AGENT_DB_PATH": str(self.db_path)}, clear=False)
        self.env.start()
        task_store.reset_initialized_for_tests()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()
        task_store.reset_initialized_for_tests()

    def test_compact_text_keeps_short_input(self) -> None:
        self.assertEqual(event_agent.compact_text_for_llm("abc", max_chars=10), "abc")

    def test_compact_text_truncates_long_input(self) -> None:
        text = "a" * 40
        compacted = event_agent.compact_text_for_llm(text, max_chars=20)
        self.assertIn("内容过长", compacted)
        self.assertLess(len(compacted), len(text) + 40)

    def test_chunk_text_splits_by_budget(self) -> None:
        chunks = event_agent.chunk_text("一\n二\n三\n四\n", max_chars=4)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk for chunk in chunks))

    def test_task_emits_lifecycle_events(self) -> None:
        fake_state = {
            "plan": [],
            "past_steps": [(("USE_TOOL", '{"tool_name": "COUNT_TEXT_CHARS", "args": {"text": "abc"}}'), '{"ok": true, "chars": 3}')],
            "current_response": "任务执行完成。",
        }

        with mock.patch("agent_edge.event_agent._run_graph", return_value=fake_state):
            task = event_agent.start_task("请统计这句话长度")
            finished = event_agent.wait_for_task(task["id"], timeout_seconds=10)

        self.assertIsNotNone(finished)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["backend"], "llama_cpp")
        events = task_store.list_events(task["id"])
        event_types = {event["type"] for event in events}
        self.assertIn(event_agent.EVENT_PLAN_REQUESTED, event_types)
        self.assertIn(event_agent.EVENT_REVIEW_REQUESTED, event_types)
        self.assertIn(event_agent.EVENT_TASK_DONE, event_types)

    def test_task_done_event_is_written_before_terminal_status(self) -> None:
        fake_state = {
            "plan": [],
            "past_steps": [],
            "current_response": "最终回复",
        }
        seen_status_at_task_done: list[str] = []
        original_add_event = task_store.add_event

        def capture_add_event(task_id: str, event_type: str, title: str, message: str = "", payload=None):
            if event_type == event_agent.EVENT_TASK_DONE:
                seen_status_at_task_done.append(task_store.get_task(task_id)["status"])
            return original_add_event(task_id, event_type, title, message, payload)

        with mock.patch("agent_edge.event_agent._run_graph", return_value=fake_state):
            with mock.patch("agent_edge.task_store.add_event", side_effect=capture_add_event):
                task = event_agent.start_task("测试最终事件顺序")
                finished = event_agent.wait_for_task(task["id"], timeout_seconds=10)

        self.assertIsNotNone(finished)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(seen_status_at_task_done, ["running"])

    def test_rejects_removed_backends(self) -> None:
        with self.assertRaises(ValueError):
            event_agent.start_task("hello", backend="mock")


if __name__ == "__main__":
    unittest.main()
