from __future__ import annotations

import unittest

from agent_edge.parsing import parse_json_list, parse_react_output


class ParsingTest(unittest.TestCase):
    def test_parse_json_list_inside_text(self) -> None:
        value = parse_json_list('计划如下：\n[{"id": 1, "kind": "learn_skill"}]')
        self.assertEqual(value[0]["id"], 1)

    def test_parse_react(self) -> None:
        thought, action, action_input = parse_react_output(
            'Thought: 读取技能\nAction: READ_SKILL\nAction Input: skills_index.md'
        )
        self.assertEqual(thought, "读取技能")
        self.assertEqual(action, "READ_SKILL")
        self.assertEqual(action_input, "skills_index.md")


if __name__ == "__main__":
    unittest.main()
