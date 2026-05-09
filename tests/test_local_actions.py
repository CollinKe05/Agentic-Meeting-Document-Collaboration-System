from __future__ import annotations

import json
import unittest

from agent_edge.local_actions import execute_local_action
from agent_edge.paths import ensure_demo_assets


class LocalActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        ensure_demo_assets()

    def test_read_skill(self) -> None:
        content = execute_local_action("READ_SKILL", "skills_index.md")
        self.assertIn("本地技能索引", content)

    def test_reject_path_traversal(self) -> None:
        observation = execute_local_action("READ_SKILL", "../README.md")
        payload = json.loads(observation)
        self.assertFalse(payload["ok"])

    def test_safe_read_text_file(self) -> None:
        observation = execute_local_action(
            "USE_TOOL",
            '{"tool_name": "SAFE_READ_TEXT_FILE", "args": {"path": "demo_input.txt"}}',
        )
        payload = json.loads(observation)
        self.assertTrue(payload["ok"])
        self.assertIn("离线", payload["content"])


if __name__ == "__main__":
    unittest.main()
