from __future__ import annotations

import unittest
from unittest import mock

from agent_edge import llm


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class LlamaCppBackendTest(unittest.TestCase):
    def test_llama_cpp_chat_returns_message_content(self) -> None:
        with mock.patch("agent_edge.llm.ensure_llama_server_running") as ensure_mock:
            with mock.patch("agent_edge.llm.requests.post") as post_mock:
                post_mock.return_value = FakeResponse(
                    {"choices": [{"message": {"content": "hello from qwen"}}]}
                )

                result = llm.llama_cpp_chat("ping")

        self.assertEqual(result, "hello from qwen")
        ensure_mock.assert_called_once()
        self.assertEqual(post_mock.call_args.kwargs["json"]["stream"], False)
        self.assertEqual(post_mock.call_args.kwargs["json"]["temperature"], 0)

    def test_llm_call_uses_llama_cpp_only(self) -> None:
        with mock.patch("agent_edge.llm.llama_cpp_chat", return_value="ok") as chat_mock:
            self.assertEqual(llm.llm_call("prompt"), "ok")
        chat_mock.assert_called_once_with("prompt")


if __name__ == "__main__":
    unittest.main()
