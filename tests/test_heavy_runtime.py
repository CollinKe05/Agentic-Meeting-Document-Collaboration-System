from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import heavy_runtime


class HeavyRuntimeTest(unittest.TestCase):
    def tearDown(self) -> None:
        heavy_runtime.cleanup_managed_processes()

    def test_exclusive_process_success_resets_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "ok.log"
            result = heavy_runtime.run_exclusive_process(
                [sys.executable, "-c", "print('done')"],
                engine_state="MINERU_RUNNING",
                cwd=None,
                env=os.environ.copy(),
                timeout_seconds=5,
                log_path=log_path,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(heavy_runtime.get_active_engine(), "IDLE")
        self.assertIn("done", result.log_tail)

    def test_exclusive_process_timeout_resets_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "timeout.log"
            with self.assertRaises(heavy_runtime.ManagedProcessError):
                heavy_runtime.run_exclusive_process(
                    [sys.executable, "-c", "import time; time.sleep(10)"],
                    engine_state="MINERU_RUNNING",
                    cwd=None,
                    env=os.environ.copy(),
                    timeout_seconds=0.2,
                    log_path=log_path,
                )

        self.assertEqual(heavy_runtime.get_active_engine(), "IDLE")

    def test_mutual_exclusion_blocks_mineru_while_llm_active(self) -> None:
        with heavy_runtime.llm_request_guard():
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(heavy_runtime.EngineBusyError):
                    heavy_runtime.run_exclusive_process(
                        [sys.executable, "-c", "print('nope')"],
                        engine_state="MINERU_RUNNING",
                        cwd=None,
                        env=os.environ.copy(),
                        timeout_seconds=5,
                        log_path=Path(tmp) / "busy.log",
                    )

        self.assertEqual(heavy_runtime.get_active_engine(), "IDLE")

    def test_mineru_wrapper_stops_and_restarts_llama(self) -> None:
        fake_result = heavy_runtime.ManagedProcessResult(
            command=("mineru",),
            returncode=0,
            log_path=Path("mineru.log"),
            log_tail="ok",
        )
        with mock.patch("agent_edge.heavy_runtime.stop_llama_server") as stop_mock:
            with mock.patch("agent_edge.heavy_runtime.ensure_llama_server_running") as start_mock:
                with mock.patch(
                    "agent_edge.heavy_runtime.run_exclusive_process", return_value=fake_result
                ) as run_mock:
                    result = heavy_runtime.run_mineru_blocking(
                        ["mineru"],
                        cwd=None,
                        env=os.environ.copy(),
                        timeout_seconds=5,
                        log_path=Path("mineru.log"),
                        restart_llama=True,
                    )

        self.assertEqual(result, fake_result)
        stop_mock.assert_called_once()
        start_mock.assert_called_once()
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
