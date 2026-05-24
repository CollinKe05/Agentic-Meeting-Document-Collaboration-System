from __future__ import annotations

import unittest

from agent_edge import event_agent
from agent_edge.perception import FakeAsrAdapter, FakeOcrAdapter, PerceptionQueue


class PerceptionTest(unittest.TestCase):
    def test_fake_asr_enqueues_high_priority_event(self) -> None:
        events = PerceptionQueue()
        adapter = FakeAsrAdapter(events)
        adapter.accept_text_segment("会议纪要", meeting_id="m1")

        event = events.get_nowait()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, event_agent.EVENT_ASR_SEGMENT_READY)
        self.assertEqual(event.payload["text"], "会议纪要")

    def test_fake_ocr_returns_markdown_shape(self) -> None:
        result = FakeOcrAdapter().parse_image("uploads/a.png")
        self.assertTrue(result["ok"])
        self.assertIn("markdown", result)


if __name__ == "__main__":
    unittest.main()
