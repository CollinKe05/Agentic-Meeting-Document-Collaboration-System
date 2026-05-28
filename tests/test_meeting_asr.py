from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import meeting_asr


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 1234
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


class MeetingAsrTest(unittest.TestCase):
    def tearDown(self) -> None:
        meeting_asr.cleanup_asr_processes()

    def test_start_and_stop_meeting_reads_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            (asr_dir / "mic_asr.py").write_text("print('fake')", encoding="utf-8")
            fake_process = FakeProcess()

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                with mock.patch("agent_edge.meeting_asr.subprocess.Popen", return_value=fake_process):
                    started = meeting_asr.start_meeting()
                    (asr_dir / "录音记录_2099-01-01_00-00-00.txt").write_text("会议内容", encoding="utf-8")
                    stopped = meeting_asr.stop_meeting()

        self.assertTrue(started["running"])
        self.assertFalse(stopped["running"])
        self.assertIn("会议内容", stopped["transcript"])

    def test_voice_input_rejects_when_meeting_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            (asr_dir / "mic_asr.py").write_text("print('fake')", encoding="utf-8")
            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                with mock.patch("agent_edge.meeting_asr.subprocess.Popen", return_value=FakeProcess()):
                    meeting_asr.start_meeting()
                    with self.assertRaises(RuntimeError):
                        meeting_asr.start_voice_input()

    def test_asr_env_includes_local_venv_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            site_packages = asr_dir / "venv" / "Lib" / "site-packages"
            sherpa_lib = site_packages / "sherpa_onnx" / "lib"
            scripts = asr_dir / "venv" / "Scripts"
            sherpa_lib.mkdir(parents=True)
            scripts.mkdir(parents=True)

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                env = meeting_asr._asr_subprocess_env()

        self.assertIn(str(site_packages), env["PYTHONPATH"])
        self.assertIn(str(sherpa_lib), env["PATH"])
        self.assertIn(str(scripts), env["PATH"])


if __name__ == "__main__":
    unittest.main()
