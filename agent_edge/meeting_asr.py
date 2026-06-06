from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import context_store
from .paths import PROJECT_ROOT, WORKSPACE_DIR


ASR_DIR = Path(os.environ.get("SHERPA_ASR_DIR", PROJECT_ROOT / "sherpa_asr" / "sherpa_asr")).expanduser()
DEFAULT_TRANSCRIPT_LIMIT = 20000
ASR_RUNTIME_DIR = PROJECT_ROOT / ".runtime" / "asr"
MEETING_RECORDS_DIR = WORKSPACE_DIR / "meeting_records"

_lock = threading.RLock()
_meeting_session: "AsrSession | None" = None
_voice_session: "AsrSession | None" = None
_last_meeting_transcript_path: Path | None = None
_last_meeting_workspace_path: Path | None = None
_last_meeting_transcript = ""
_current_meeting_context_id: str | None = None
_last_meeting_context_id: str | None = None


@dataclass
class AsrSession:
    kind: str
    process: subprocess.Popen[bytes]
    started_at: float
    backend: str = "native"
    known_files: set[Path] = field(default_factory=set)
    transcript_path: Path | None = None
    windows_pid_file: Path | None = None
    stop_file: Path | None = None


def start_meeting() -> dict[str, Any]:
    global _last_meeting_transcript, _last_meeting_transcript_path, _last_meeting_workspace_path, _meeting_session
    global _current_meeting_context_id
    with _lock:
        if _is_live(_voice_session):
            raise RuntimeError("短语音输入正在使用麦克风，请先停止语音输入。")
        if _is_live(_meeting_session):
            return meeting_status()
        _last_meeting_transcript_path = None
        _last_meeting_workspace_path = None
        _last_meeting_transcript = ""
        _meeting_session = _start_asr_session("meeting")
        _current_meeting_context_id = _create_running_meeting_context()
        status = meeting_status()
        status["context_id"] = _current_meeting_context_id
        return status


def stop_meeting() -> dict[str, Any]:
    global _last_meeting_transcript, _last_meeting_transcript_path, _last_meeting_workspace_path, _meeting_session
    global _current_meeting_context_id, _last_meeting_context_id
    with _lock:
        session = _meeting_session
        _meeting_session = None
        context_id = _current_meeting_context_id
        _current_meeting_context_id = None
        cached_path = _last_meeting_transcript_path
        cached_workspace_path = _last_meeting_workspace_path
        cached_transcript = _last_meeting_transcript

    result = _stop_session(session, kind="meeting")
    transcript = str(result.get("transcript") or "")
    if transcript:
        workspace_path = _persist_meeting_transcript(
            transcript=transcript,
            source_path=Path(str(result["transcript_path"])) if result.get("transcript_path") else None,
        )
        _attach_workspace_record(result, workspace_path)
        context_id = _complete_meeting_context(
            context_id=context_id,
            transcript=transcript,
            source_path=Path(str(result["transcript_path"])) if result.get("transcript_path") else None,
            workspace_path=workspace_path,
        )
        result["context_id"] = context_id
        with _lock:
            raw_path = result.get("transcript_path")
            _last_meeting_transcript_path = Path(str(raw_path)) if raw_path else None
            _last_meeting_workspace_path = workspace_path
            _last_meeting_transcript = transcript
            _last_meeting_context_id = context_id
    elif session is None and cached_transcript:
        result["transcript_path"] = str(cached_path) if cached_path else None
        _attach_workspace_record(result, cached_workspace_path)
        result["transcript"] = cached_transcript
        if _last_meeting_context_id:
            result["context_id"] = _last_meeting_context_id
    return result


def meeting_status() -> dict[str, Any]:
    with _lock:
        session = _meeting_session
        if session is None and _last_meeting_transcript:
            result = {
                "status": "waiting",
                "running": False,
                "backend": _resolve_asr_backend(),
                "transcript_path": str(_last_meeting_transcript_path) if _last_meeting_transcript_path else None,
                "transcript": _last_meeting_transcript,
            }
            if _last_meeting_context_id:
                result["context_id"] = _last_meeting_context_id
            _attach_workspace_record(result, _last_meeting_workspace_path)
            return result
        result = _status_for_session(session, idle_label="waiting", kind="meeting")
        if _current_meeting_context_id:
            result["context_id"] = _current_meeting_context_id
        return result


def meeting_summary_prompt() -> str:
    status = meeting_status()
    transcript = str(status.get("transcript") or "").strip()
    if not transcript:
        transcript = _active_meeting_transcript()
    if not transcript:
        raise ValueError("当前没有可总结的会议记录。")
    return (
        "请基于下面的实时会议转写生成会议纪要，包含：主题、关键结论、行动项、风险或待确认事项。\n\n"
        f"<meeting_transcript>\n{transcript}\n</meeting_transcript>"
    )


def _active_meeting_transcript() -> str:
    active = context_store.get_active_context(include_context=True)
    context = active.get("context") if active.get("focus_state") == "MEETING_ACTIVE" else None
    if not context:
        meetings = context_store.list_contexts(kind="meeting", limit=1)
        context = meetings[0] if meetings else None
    if not context:
        return ""
    stored = context_store.get_context(str(context["id"]), include_artifacts=True, include_chunks=True)
    if not stored:
        return ""
    for artifact in stored.get("artifacts") or []:
        if artifact.get("artifact_type") == "transcript":
            try:
                path = WORKSPACE_DIR / str(artifact.get("path") or "")
                if path.is_file():
                    return path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return "\n".join(
        str(chunk.get("text") or "")
        for chunk in stored.get("chunks") or []
        if chunk.get("chunk_type") == "transcript_segment"
    )


def list_meeting_records(*, limit: int = 50) -> list[dict[str, Any]]:
    if not MEETING_RECORDS_DIR.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in MEETING_RECORDS_DIR.glob("*.txt"):
        if not path.is_file():
            continue
        stat = path.stat()
        records.append(
            {
                "name": path.name,
                "path": path.relative_to(WORKSPACE_DIR).as_posix(),
                "absolute_path": str(path),
                "size": stat.st_size,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            }
        )
    records.sort(key=lambda item: item["updated_at"], reverse=True)
    return records[:limit]


def start_voice_input() -> dict[str, Any]:
    global _voice_session
    with _lock:
        if _is_live(_meeting_session):
            raise RuntimeError("会议记录正在使用麦克风，请先关闭会议记录。")
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
        return _status_for_session(session, idle_label="idle", kind="voice")


def cleanup_asr_processes() -> None:
    stop_voice_input()
    stop_meeting()


def _start_asr_session(kind: str) -> AsrSession:
    if not ASR_DIR.exists():
        raise FileNotFoundError(f"sherpa_asr 目录不存在：{ASR_DIR}")
    script = ASR_DIR / "mic_asr.py"
    if not script.exists():
        raise FileNotFoundError(f"mic_asr.py 不存在：{script}")

    backend = _resolve_asr_backend()
    known = set(_candidate_transcripts())
    log_path = PROJECT_ROOT / ".runtime" / "logs" / f"{kind}-asr.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ASR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stop_file = ASR_RUNTIME_DIR / f"{kind}-asr.stop"
    stop_file.unlink(missing_ok=True)

    if backend == "windows":
        _assert_windows_asr_input_available()
        cmd, cwd, env, windows_pid_file = _windows_asr_process_spec(kind, script, stop_file=stop_file)
    else:
        _assert_asr_input_available()
        cmd = [_python_for_asr(), str(script)]
        cwd = str(ASR_DIR)
        env = _asr_subprocess_env()
        env["SHERPA_ASR_STOP_FILE"] = str(stop_file)
        windows_pid_file = None

    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **_new_process_group_kwargs(),
        )
    return AsrSession(
        kind=kind,
        process=process,
        started_at=time.time(),
        backend=backend,
        known_files=known,
        windows_pid_file=windows_pid_file,
        stop_file=stop_file,
    )


def _stop_session(session: AsrSession | None, *, kind: str) -> dict[str, Any]:
    if session is None:
        return {"status": "waiting" if kind == "meeting" else "idle", "running": False, "transcript": ""}
    if _is_live(session):
        _request_session_stop(session, grace_seconds=float(os.environ.get("ASR_STOP_GRACE_SECONDS", "8")))
    transcript_path = _discover_transcript_path(session)
    transcript = _read_transcript(transcript_path, kind=kind) if transcript_path else ""
    return {
        "status": "waiting" if kind == "meeting" else "idle",
        "running": False,
        "backend": session.backend,
        "transcript_path": str(transcript_path) if transcript_path else None,
        "transcript": transcript,
    }


def _persist_meeting_transcript(*, transcript: str, source_path: Path | None) -> Path:
    MEETING_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    if source_path is not None:
        stem = source_path.stem
    else:
        stem = "meeting"
    safe_stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", stem).strip("_") or "meeting"
    if not safe_stem.startswith(("meeting_", "录音记录_", "錄音記錄_")):
        safe_stem = f"meeting_{safe_stem}"
    target = MEETING_RECORDS_DIR / f"{safe_stem}.txt"
    if target.exists():
        target = MEETING_RECORDS_DIR / f"{safe_stem}_{int(time.time())}.txt"
    target.write_text(transcript, encoding="utf-8", newline="\n")
    return target


def _attach_workspace_record(result: dict[str, Any], workspace_path: Path | None) -> None:
    if workspace_path is None:
        return
    try:
        rel_path = workspace_path.relative_to(WORKSPACE_DIR).as_posix()
    except ValueError:
        rel_path = str(workspace_path)
    result["workspace_transcript_path"] = str(workspace_path)
    result["workspace_transcript_relpath"] = rel_path


def _create_running_meeting_context() -> str:
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    context_id = f"meeting_{int(time.time())}"
    context = context_store.create_context(
        kind="meeting",
        title=f"会议记录 {started}",
        summary="会议记录进行中",
        status="running",
        metadata={"started_at": started, "backend": _resolve_asr_backend()},
        context_id=context_id,
    )
    context_store.set_active_context(
        focus_state="MEETING_ACTIVE",
        context_id=context["id"],
        mode="soft",
        entered_reason="meeting_started",
        expires_after_turns=4,
    )
    return str(context["id"])


def _complete_meeting_context(
    *,
    context_id: str | None,
    transcript: str,
    source_path: Path | None,
    workspace_path: Path | None,
) -> str:
    if context_id and context_store.get_context(context_id, include_artifacts=False):
        cid = context_id
    else:
        cid = f"meeting_{int(time.time())}"
        context_store.create_context(
            kind="meeting",
            title=f"会议记录 {time.strftime('%Y-%m-%d %H:%M:%S')}",
            status="active",
            context_id=cid,
        )

    rel_workspace = _workspace_rel(workspace_path) if workspace_path else ""
    title_source = workspace_path.name if workspace_path else (source_path.name if source_path else "meeting")
    summary = _meeting_summary_preview(transcript)
    context_store.update_context(
        cid,
        title=f"{title_source} 会议记录",
        summary=summary,
        source_path=rel_workspace or (str(source_path) if source_path else ""),
        status="active",
        metadata={
            "source_path": str(source_path) if source_path else "",
            "workspace_transcript_path": str(workspace_path) if workspace_path else "",
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    if workspace_path:
        context_store.add_artifact(cid, "transcript", rel_workspace, name=workspace_path.name)
    if source_path:
        context_store.add_artifact(cid, "raw_transcript", str(source_path), name=source_path.name)
    context_store.replace_chunks(cid, "transcript_segment")
    context_store.add_chunks(
        cid,
        "transcript_segment",
        _meeting_segments(transcript),
        metadata={"workspace_transcript_path": rel_workspace},
    )
    context_store.set_active_context(
        focus_state="MEETING_ACTIVE",
        context_id=cid,
        mode="soft",
        entered_reason="meeting_stopped",
        expires_after_turns=4,
    )
    return cid


def _workspace_rel(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(WORKSPACE_DIR).as_posix()
    except ValueError:
        return str(path)


def _meeting_segments(transcript: str) -> list[str]:
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    segments = [line for line in lines if re.search(r"\[\d{1,2}:\d{2}", line)]
    return segments or context_store.split_text(transcript, max_chars=1000, overlap=80)


def _meeting_summary_preview(transcript: str) -> str:
    content_lines = [
        line.strip()
        for line in transcript.splitlines()
        if line.strip() and not line.startswith("=") and "开始时间" not in line and line.strip() != "录音记录"
    ]
    return " ".join(content_lines)[:300]


def _status_for_session(session: AsrSession | None, *, idle_label: str, kind: str) -> dict[str, Any]:
    if session is None or not _is_live(session):
        transcript_path = _discover_transcript_path(session) if session else None
        transcript = _read_transcript(transcript_path, kind=kind) if transcript_path else ""
        return {
            "status": idle_label,
            "running": False,
            "backend": session.backend if session else _resolve_asr_backend(),
            "transcript_path": str(transcript_path) if transcript_path else None,
            "transcript": transcript,
        }
    transcript_path = _discover_transcript_path(session)
    session.transcript_path = transcript_path or session.transcript_path
    transcript = _read_transcript(session.transcript_path, kind=kind) if session.transcript_path else ""
    return {
        "status": "running",
        "running": True,
        "pid": session.process.pid,
        "backend": session.backend,
        "transcript_path": str(session.transcript_path) if session.transcript_path else None,
        "transcript": transcript,
    }


def _resolve_asr_backend() -> str:
    configured = os.environ.get("SHERPA_ASR_BACKEND", os.environ.get("ASR_BACKEND", "auto")).strip().lower()
    if configured in {"windows", "win", "windows_bridge"}:
        return "windows"
    if configured in {"native", "local", "wsl"}:
        return "native"
    if configured != "auto":
        raise ValueError("SHERPA_ASR_BACKEND 只能是 auto、native 或 windows")
    if _is_wsl() and _windows_asr_bridge_available():
        return "windows"
    return "native"


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
    if os.name != "nt":
        return env
    _inject_windows_asr_env(env, separator=os.pathsep)
    return env


def _assert_asr_input_available() -> None:
    if os.environ.get("ASR_SKIP_INPUT_DEVICE_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001 - API boundary should explain local audio failure
        raise RuntimeError(f"ASR 麦克风设备检查失败：{type(exc).__name__}: {exc}") from exc

    if not _devices_have_input(devices):
        raise RuntimeError(
            "ASR 未检测到可用麦克风输入设备。当前如果运行在 WSL 中，"
            "请使用 Windows ASR 桥接，或把 Windows 麦克风暴露给 Ubuntu。"
        )


def _assert_windows_asr_input_available() -> None:
    if os.environ.get("ASR_SKIP_INPUT_DEVICE_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    _assert_windows_interop_available()
    ASR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    probe = ASR_RUNTIME_DIR / "probe-windows-asr-input.ps1"
    paths = _windows_asr_paths()
    probe.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"Set-Location -LiteralPath {_ps_literal(paths['asr_dir'])}",
                f"$env:PYTHONPATH = {_ps_literal(paths['site_packages'])}",
                f"$env:PATH = {_ps_literal(paths['sherpa_lib'] + ';' + paths['scripts'] + ';')} + $env:PATH",
                (
                    f"& {_ps_literal(paths['python'])} -c "
                    '"import sounddevice as sd; '
                    "devices=sd.query_devices(); "
                    "print(devices); "
                    "raise SystemExit(0 if any(int(d.get('max_input_channels', 0)) > 0 for d in devices) else 3)\""
                ),
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        _windows_powershell_command(probe),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=float(os.environ.get("ASR_INPUT_CHECK_TIMEOUT_SECONDS", "10")),
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Windows ASR 桥接未检测到可用麦克风：{detail or '无详细输出'}")


def _windows_asr_process_spec(kind: str, script: Path, *, stop_file: Path) -> tuple[list[str], str, dict[str, str], Path]:
    _assert_windows_interop_available()
    ASR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    launcher = ASR_RUNTIME_DIR / f"{kind}-asr-launch.ps1"
    pid_file = ASR_RUNTIME_DIR / f"{kind}-asr-windows.pid"
    paths = _windows_asr_paths()
    launcher.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"Set-Location -LiteralPath {_ps_literal(paths['asr_dir'])}",
                f"$env:PYTHONPATH = {_ps_literal(paths['site_packages'])}",
                f"$env:PATH = {_ps_literal(paths['sherpa_lib'] + ';' + paths['scripts'] + ';')} + $env:PATH",
                f"$env:SHERPA_ASR_STOP_FILE = {_ps_literal(_path_to_windows(stop_file))}",
                (
                    f"$proc = Start-Process -FilePath {_ps_literal(paths['python'])} "
                    f"-ArgumentList @({_ps_literal(_path_to_windows(script))}) "
                    f"-WorkingDirectory {_ps_literal(paths['asr_dir'])} -NoNewWindow -PassThru"
                ),
                f"[System.IO.File]::WriteAllText({_ps_literal(_path_to_windows(pid_file))}, [string]$proc.Id)",
                "Wait-Process -Id $proc.Id",
                "$proc.Refresh()",
                "exit $proc.ExitCode",
            ]
        ),
        encoding="utf-8",
    )
    cmd = _windows_powershell_command(launcher)
    return cmd, str(PROJECT_ROOT), os.environ.copy(), pid_file


def _windows_asr_paths() -> dict[str, str]:
    site_packages = ASR_DIR / "venv" / "Lib" / "site-packages"
    scripts = ASR_DIR / "venv" / "Scripts"
    sherpa_lib = site_packages / "sherpa_onnx" / "lib"
    return {
        "python": _windows_python_path(),
        "asr_dir": _path_to_windows(ASR_DIR),
        "site_packages": _path_to_windows(site_packages),
        "scripts": _path_to_windows(scripts),
        "sherpa_lib": _path_to_windows(sherpa_lib),
    }


def _windows_asr_bridge_available() -> bool:
    configured_python = os.environ.get("SHERPA_ASR_WINDOWS_PYTHON")
    python_ok = bool(configured_python) or _default_windows_python_posix_path().exists()
    site_packages_ok = (ASR_DIR / "venv" / "Lib" / "site-packages").exists()
    return python_ok and site_packages_ok


def _windows_python_path() -> str:
    configured = os.environ.get("SHERPA_ASR_WINDOWS_PYTHON")
    if configured:
        return _as_windows_path_string(configured)
    return _path_to_windows(_default_windows_python_posix_path())


def _default_windows_python_posix_path() -> Path:
    parts = ASR_DIR.as_posix().split("/")
    if len(parts) >= 5 and parts[1] == "mnt" and parts[3].lower() == "users":
        return Path("/mnt") / parts[2] / "Users" / parts[4] / "miniforge3" / "python.exe"
    return Path("/mnt/c/Users/19653/miniforge3/python.exe")


def _inject_windows_asr_env(env: dict[str, str], *, separator: str) -> None:
    site_packages = ASR_DIR / "venv" / "Lib" / "site-packages"
    scripts = ASR_DIR / "venv" / "Scripts"
    sherpa_lib = site_packages / "sherpa_onnx" / "lib"

    if site_packages.exists():
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(site_packages)
            if not current_pythonpath
            else str(site_packages) + separator + current_pythonpath
        )

    path_parts = [str(path) for path in (sherpa_lib, scripts) if path.exists()]
    if path_parts:
        env["PATH"] = separator.join(path_parts + [env.get("PATH", "")])


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
    candidates: list[Path] = []
    for pattern in ("录音记录_*.txt", "褰曢煶璁板綍_*.txt"):
        candidates.extend(path for path in ASR_DIR.glob(pattern) if path.is_file())
    transcript = ASR_DIR / "transcript.txt"
    if transcript.exists():
        candidates.append(transcript)
    return list(dict.fromkeys(candidates))


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


def _read_transcript(path: Path | None, *, kind: str = "meeting") -> str:
    if path is None or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    limit = int(os.environ.get("ASR_TRANSCRIPT_PREVIEW_CHARS", str(DEFAULT_TRANSCRIPT_LIMIT)))
    text = text[-limit:]
    if kind == "voice":
        return _format_voice_transcript(text)
    return text


def _format_voice_transcript(text: str) -> str:
    segments: list[tuple[str, int, str]] = []
    for index, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+?)\s*$", line)
        if match:
            sentence = match.group(2).strip()
            if sentence:
                segments.append((match.group(1), index, sentence))
    if segments:
        return " ".join(sentence for _, _, sentence in sorted(segments))
    return _strip_transcript_log_header(text)


def _strip_transcript_log_header(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if set(line) <= {"="}:
            continue
        if line in {"录音记录", "錄音記錄"}:
            continue
        if line.startswith(("开始时间", "開始時間", "结束时间", "結束時間")):
            continue
        lines.append(line)
    return " ".join(lines)


def _devices_have_input(devices: Any) -> bool:
    try:
        for device in devices:
            if int(device.get("max_input_channels", 0)) > 0:
                return True
    except Exception:
        return bool(str(devices).strip())
    return False


def _is_live(session: AsrSession | None) -> bool:
    return session is not None and session.process.poll() is None


def _is_wsl() -> bool:
    if os.name != "posix":
        return False
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in release or "wsl" in release


def _as_windows_path_string(value: str) -> str:
    if len(value) > 1 and value[1] == ":":
        return value
    return _path_to_windows(Path(value))


def _path_to_windows(path: Path) -> str:
    raw = str(path)
    if len(raw) > 1 and raw[1] == ":":
        return raw
    if os.name == "nt":
        return str(path)
    posix = path.as_posix()
    parts = posix.split("/")
    if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    raise RuntimeError(f"无法把路径转换成 Windows 路径：{path}")


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell_exe() -> str:
    return os.environ.get("SHERPA_ASR_WINDOWS_POWERSHELL", "powershell.exe")


def _windows_cmd_exe() -> str:
    configured = os.environ.get("SHERPA_ASR_WINDOWS_CMD")
    if configured:
        return configured
    if os.name == "posix":
        return "cmd.exe"
    return "cmd.exe"


def _assert_windows_interop_available() -> None:
    if os.name != "posix":
        return
    marker = Path("/proc/sys/fs/binfmt_misc/WSLInterop")
    if not marker.exists():
        raise RuntimeError(
            "当前 WSL 没有注册 WSLInterop，Ubuntu 不能直接启动 Windows 的 cmd.exe/powershell.exe。"
            "请在 /etc/wsl.conf 中启用 [interop] enabled=true、appendWindowsPath=true，"
            "然后在 Windows PowerShell 执行 wsl --shutdown，再重新进入 Ubuntu 启动 Agent。"
        )
    result = subprocess.run(
        ["/bin/sh", "-lc", "cmd.exe /d /c exit 0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "当前 WSL 无法执行 Windows 进程，所以不能使用 Windows 麦克风桥接。"
            "请执行 wsl --shutdown 后重启 WSL；如果仍失败，请检查 WSL interop 是否被禁用。"
            f" 原始错误：{detail}"
        )


def _windows_powershell_command(script: Path) -> list[str]:
    win_script = _path_to_windows(script)
    if os.name == "posix":
        wrapper = script.with_suffix(".cmd")
        wrapper.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{win_script}"',
                    "exit /b %ERRORLEVEL%",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        shell_command = f"{_windows_cmd_exe()} /d /c {_sh_literal(_path_to_windows(wrapper))}"
        return ["/bin/sh", "-lc", shell_command]
    return [_powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win_script]


def _windows_taskkill_command(pid: int) -> list[str]:
    if os.name == "posix":
        return ["/bin/sh", "-lc", f"taskkill.exe /PID {pid} /T /F"]
    return ["taskkill.exe", "/PID", str(pid), "/T", "/F"]


def _sh_literal(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


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


def _request_session_stop(session: AsrSession, *, grace_seconds: float) -> None:
    if session.stop_file:
        try:
            session.stop_file.parent.mkdir(parents=True, exist_ok=True)
            session.stop_file.write_text("stop\n", encoding="utf-8")
        except OSError:
            pass

    try:
        session.process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    if session.backend == "windows" and session.windows_pid_file:
        _terminate_windows_pid_file(session.windows_pid_file)
    _terminate_process_group(session.process, grace_seconds=grace_seconds)


def _terminate_windows_pid_file(pid_file: Path) -> None:
    try:
        raw = pid_file.read_text(encoding="utf-8", errors="ignore").strip()
        pid = int(raw)
    except Exception:
        return
    subprocess.run(
        _windows_taskkill_command(pid),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=float(os.environ.get("ASR_STOP_GRACE_SECONDS", "5")),
        check=False,
    )
