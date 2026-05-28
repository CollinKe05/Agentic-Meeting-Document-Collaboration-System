from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT


ASR_DIR = Path(os.environ.get("SHERPA_ASR_DIR", PROJECT_ROOT / "sherpa_asr" / "sherpa_asr")).expanduser()
DEFAULT_TRANSCRIPT_LIMIT = 20000

_lock = threading.RLock()
_meeting_session: "AsrSession | None" = None
_voice_session: "AsrSession | None" = None


@dataclass
class AsrSession:
    kind: str
    process: subprocess.Popen[bytes]
    started_at: float
    known_files: set[Path] = field(default_factory=set)
    transcript_path: Path | None = None


def start_meeting() -> dict[str, Any]:
    global _meeting_session
    with _lock:
        if _is_live(_voice_session):
            raise RuntimeError("短语音输入正在使用麦克风，请先停止语音输入")
        if _is_live(_meeting_session):
            return meeting_status()
        _meeting_session = _start_asr_session("meeting")
        return meeting_status()


def stop_meeting() -> dict[str, Any]:
    global _meeting_session
    with _lock:
        session = _meeting_session
        _meeting_session = None
    return _stop_session(session, kind="meeting")


def meeting_status() -> dict[str, Any]:
    with _lock:
        session = _meeting_session
        return _status_for_session(session, idle_label="waiting")


def meeting_summary_prompt() -> str:
    status = meeting_status()
    transcript = str(status.get("transcript") or "").strip()
    if not transcript:
        raise ValueError("当前没有可总结的会议记录")
    return (
        "请基于下面的实时会议转写生成会议纪要，包含：主题、关键结论、行动项、风险或待确认事项。\n\n"
        f"<meeting_transcript>\n{transcript}\n</meeting_transcript>"
    )


def start_voice_input() -> dict[str, Any]:
    global _voice_session
    with _lock:
        if _is_live(_meeting_session):
            raise RuntimeError("会议记录正在使用麦克风，请先关闭会议记录")
        if _is_live(_voice_session):
            return voice_input_status()
        _voice_session = _start_asr_session("voice")
        return voice_input_status()


def stop_voice_input() -> dict[str, Any]:
    global _voice_session
    with _lock:
        session = _voice_session
        _voice_session = None
    return _stop_session(session, kind="voice")


def voice_input_status() -> dict[str, Any]:
    with _lock:
        session = _voice_session
        return _status_for_session(session, idle_label="idle")


def cleanup_asr_processes() -> None:
    stop_voice_input()
    stop_meeting()


def _start_asr_session(kind: str) -> AsrSession:
    if not ASR_DIR.exists():
        raise FileNotFoundError(f"sherpa_asr directory not found: {ASR_DIR}")
    script = ASR_DIR / "mic_asr.py"
    if not script.exists():
        raise FileNotFoundError(f"mic_asr.py not found: {script}")

    known = set(_candidate_transcripts())
    log_path = PROJECT_ROOT / ".runtime" / "logs" / f"{kind}-asr.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_python_for_asr(), str(script)]
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=str(ASR_DIR),
            env=_asr_subprocess_env(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **_new_process_group_kwargs(),
        )
    return AsrSession(kind=kind, process=process, started_at=time.time(), known_files=known)


def _stop_session(session: AsrSession | None, *, kind: str) -> dict[str, Any]:
    if session is None:
        return {"status": "waiting" if kind == "meeting" else "idle", "running": False, "transcript": ""}
    if _is_live(session):
        _terminate_process_group(session.process, grace_seconds=float(os.environ.get("ASR_STOP_GRACE_SECONDS", "5")))
    transcript_path = _discover_transcript_path(session)
    transcript = _read_transcript(transcript_path) if transcript_path else ""
    return {
        "status": "waiting" if kind == "meeting" else "idle",
        "running": False,
        "transcript_path": str(transcript_path) if transcript_path else None,
        "transcript": transcript,
    }


def _status_for_session(session: AsrSession | None, *, idle_label: str) -> dict[str, Any]:
    if session is None or not _is_live(session):
        transcript_path = _discover_transcript_path(session) if session else None
        transcript = _read_transcript(transcript_path) if transcript_path else ""
        return {
            "status": idle_label,
            "running": False,
            "transcript_path": str(transcript_path) if transcript_path else None,
            "transcript": transcript,
        }
    transcript_path = _discover_transcript_path(session)
    session.transcript_path = transcript_path or session.transcript_path
    transcript = _read_transcript(session.transcript_path) if session.transcript_path else ""
    return {
        "status": "running",
        "running": True,
        "pid": session.process.pid,
        "transcript_path": str(session.transcript_path) if session.transcript_path else None,
        "transcript": transcript,
    }


def _python_for_asr() -> str:
    configured = os.environ.get("SHERPA_ASR_PYTHON")
    if configured:
        return configured
    windows_venv = ASR_DIR / "venv" / "Scripts" / "python.exe"
    if os.name == "nt" and windows_venv.exists() and _python_executable_usable(windows_venv):
        return str(windows_venv)
    return sys.executable


def _asr_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    site_packages = ASR_DIR / "venv" / "Lib" / "site-packages"
    scripts = ASR_DIR / "venv" / "Scripts"
    sherpa_lib = site_packages / "sherpa_onnx" / "lib"

    if site_packages.exists():
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(site_packages)
            if not current_pythonpath
            else str(site_packages) + os.pathsep + current_pythonpath
        )

    path_parts = [str(path) for path in (sherpa_lib, scripts) if path.exists()]
    if path_parts:
        env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])

    return env


def _python_executable_usable(path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(path), "-c", "import sys; print(sys.executable)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001 - broken local venvs should just be skipped
        return False
    return result.returncode == 0


def _candidate_transcripts() -> list[Path]:
    if not ASR_DIR.exists():
        return []
    candidates = list(ASR_DIR.glob("录音记录_*.txt"))
    transcript = ASR_DIR / "transcript.txt"
    if transcript.exists():
        candidates.append(transcript)
    return candidates


def _discover_transcript_path(session: AsrSession | None) -> Path | None:
    candidates = _candidate_transcripts()
    if not candidates:
        return None
    if session is None:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    fresh = [path for path in candidates if path not in session.known_files or path.stat().st_mtime >= session.started_at - 1]
    if not fresh:
        return session.transcript_path
    return max(fresh, key=lambda path: path.stat().st_mtime)


def _read_transcript(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    limit = int(os.environ.get("ASR_TRANSCRIPT_PREVIEW_CHARS", str(DEFAULT_TRANSCRIPT_LIMIT)))
    return text[-limit:]


def _is_live(session: AsrSession | None) -> bool:
    return session is not None and session.process.poll() is None


def _new_process_group_kwargs() -> dict[str, object]:
    if os.name == "posix":
        return {"start_new_session": True}
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": creationflags} if creationflags else {}


def _terminate_process_group(process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=grace_seconds)
