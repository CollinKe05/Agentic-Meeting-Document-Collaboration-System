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
                with mock.patch("agent_edge.meeting_asr._assert_asr_input_available"):
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
                with mock.patch("agent_edge.meeting_asr._assert_asr_input_available"):
                    with mock.patch("agent_edge.meeting_asr.subprocess.Popen", return_value=FakeProcess()):
                        meeting_asr.start_meeting()
                        with self.assertRaises(RuntimeError):
                            meeting_asr.start_voice_input()

    def test_stop_meeting_writes_stop_file_for_graceful_flush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asr_dir = root / "asr"
            runtime_dir = root / "runtime"
            asr_dir.mkdir()
            (asr_dir / "mic_asr.py").write_text("print('fake')", encoding="utf-8")

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                with mock.patch("agent_edge.meeting_asr.ASR_RUNTIME_DIR", runtime_dir):
                    with mock.patch("agent_edge.meeting_asr._assert_asr_input_available"):
                        with mock.patch("agent_edge.meeting_asr.subprocess.Popen", return_value=FakeProcess()):
                            meeting_asr.start_meeting()
                            meeting_asr.stop_meeting()
                            self.assertTrue((runtime_dir / "meeting-asr.stop").exists())

    def test_asr_env_includes_local_venv_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            site_packages = asr_dir / "venv" / "Lib" / "site-packages"
            sherpa_lib = site_packages / "sherpa_onnx" / "lib"
            scripts = asr_dir / "venv" / "Scripts"
            sherpa_lib.mkdir(parents=True)
            scripts.mkdir(parents=True)

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                with mock.patch("agent_edge.meeting_asr.os.name", "nt"):
                    env = meeting_asr._asr_subprocess_env()

        self.assertIn(str(site_packages), env["PYTHONPATH"])
        self.assertIn(str(sherpa_lib), env["PATH"])
        self.assertIn(str(scripts), env["PATH"])

    def test_asr_env_does_not_inject_windows_venv_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            (asr_dir / "venv" / "Lib" / "site-packages").mkdir(parents=True)

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                with mock.patch("agent_edge.meeting_asr.os.name", "posix"):
                    env = meeting_asr._asr_subprocess_env()

        self.assertNotIn(str(asr_dir / "venv" / "Lib" / "site-packages"), env.get("PYTHONPATH", ""))

    def test_auto_backend_uses_windows_bridge_on_wsl_when_available(self) -> None:
        with mock.patch.dict("os.environ", {"SHERPA_ASR_BACKEND": "auto"}, clear=False):
            with mock.patch("agent_edge.meeting_asr._is_wsl", return_value=True):
                with mock.patch("agent_edge.meeting_asr._windows_asr_bridge_available", return_value=True):
                    self.assertEqual(meeting_asr._resolve_asr_backend(), "windows")

    def test_wsl_uses_cmd_to_launch_powershell_script(self) -> None:
        script = meeting_asr.PROJECT_ROOT / ".runtime" / "test-powershell-probe.ps1"
        wrapper = script.with_suffix(".cmd")
        script.parent.mkdir(parents=True, exist_ok=True)
        try:
            with mock.patch("agent_edge.meeting_asr.os.name", "posix"):
                command = meeting_asr._windows_powershell_command(script)

            self.assertEqual(command[:2], ["/bin/sh", "-lc"])
            self.assertIn("cmd.exe /d /c", command[2])
            self.assertIn("test-powershell-probe.cmd", command[2])
            self.assertIn("powershell.exe", wrapper.read_text(encoding="utf-8"))
        finally:
            script.unlink(missing_ok=True)
            wrapper.unlink(missing_ok=True)

    def test_candidate_transcripts_accepts_real_chinese_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asr_dir = Path(tmp)
            transcript = asr_dir / "录音记录_2099-01-01_00-00-00.txt"
            transcript.write_text("会议内容", encoding="utf-8")

            with mock.patch("agent_edge.meeting_asr.ASR_DIR", asr_dir):
                candidates = meeting_asr._candidate_transcripts()

        self.assertIn(transcript, candidates)

    def test_voice_transcript_returns_only_content_in_time_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "录音记录_2099-01-01_00-00-00.txt"
            transcript.write_text(
                "\n".join(
                    [
                        "============================================================",
                        "录音记录",
                        "开始时间：2099-01-01 00:00:00",
                        "============================================================",
                        "[17:10:03] 第二段话",
                        "[17:10:01] 第一段话",
                    ]
                ),
                encoding="utf-8",
            )

            text = meeting_asr._read_transcript(transcript, kind="voice")

        self.assertEqual(text, "第一段话 第二段话")


if __name__ == "__main__":
    unittest.main()
