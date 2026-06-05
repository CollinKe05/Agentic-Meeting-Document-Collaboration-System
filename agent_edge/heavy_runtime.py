from __future__ import annotations

import atexit
import hashlib
import json
import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal, Sequence
from uuid import uuid4

import requests

from .paths import PROJECT_ROOT


EngineState = Literal["IDLE", "LLM_RUNNING", "ASR_STREAMING", "OCR_RUNNING"]

RUNTIME_DIR = Path(os.environ.get("AGENT_RUNTIME_DIR", PROJECT_ROOT / ".runtime")).expanduser()
DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_LLAMA_CPP_MODEL = "qwen2.5-1.5b-instruct-q4_k_m"
DEFAULT_LLAMA_CPP_MODEL_PATH = RUNTIME_DIR / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_LLAMA_CPP_THREADS = 4
DEFAULT_LLAMA_CPP_CTX_SIZE = 4096
LLAMA_MODEL_SELECTION_PATH = RUNTIME_DIR / "selected_llama_model.json"

_lock = threading.RLock()
_active_engine: EngineState = "IDLE"
_llama_process: subprocess.Popen[bytes] | None = None
_resource_tokens: dict[str, dict[str, Any]] = {}


class EngineBusyError(RuntimeError):
    pass


class ManagedProcessError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        log_path: Path | None = None,
        log_tail: str = "",
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.log_path = log_path
        self.log_tail = log_tail


@dataclass(frozen=True)
class ManagedProcessResult:
    command: tuple[str, ...]
    returncode: int
    log_path: Path
    log_tail: str


@dataclass(frozen=True)
class LlamaCppModelInfo:
    id: str
    name: str
    path: str
    size_bytes: int
    selected: bool


def get_active_engine() -> EngineState:
    with _lock:
        return _active_engine


def get_llama_cpp_base_url() -> str:
    return os.environ.get("LLAMA_CPP_BASE_URL", DEFAULT_LLAMA_CPP_BASE_URL).rstrip("/")


def get_llama_cpp_model() -> str:
    selected = _load_selected_llama_model()
    if selected:
        return str(selected.get("name") or Path(str(selected.get("path", ""))).stem)
    return os.environ.get("LLAMA_CPP_MODEL", DEFAULT_LLAMA_CPP_MODEL)


def get_llama_cpp_model_path() -> Path:
    selected = _load_selected_llama_model()
    if selected and selected.get("path"):
        return Path(str(selected["path"])).expanduser()
    return Path(os.environ.get("LLAMA_CPP_MODEL_PATH", str(DEFAULT_LLAMA_CPP_MODEL_PATH))).expanduser()


def list_llama_cpp_models() -> list[dict[str, Any]]:
    current_path = get_llama_cpp_model_path().resolve()
    models: list[LlamaCppModelInfo] = []
    seen: set[Path] = set()
    for directory in _llama_model_search_dirs():
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.gguf"), key=lambda item: item.name.lower()):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            models.append(_model_info(resolved, selected=resolved == current_path))

    if current_path.exists() and current_path not in seen:
        models.insert(0, _model_info(current_path, selected=True))

    return [model.__dict__ for model in models]


def get_current_llama_cpp_model() -> dict[str, Any]:
    path = get_llama_cpp_model_path().resolve()
    return _model_info(path, selected=True).__dict__


def select_llama_cpp_model(model_id: str) -> dict[str, Any]:
    global _llama_process

    normalized_id = str(model_id or "").strip()
    if not normalized_id:
        raise ValueError("model_id is required")

    with _lock:
        if _active_engine != "IDLE":
            raise EngineBusyError(f"Cannot switch model while {_active_engine} is active")

    models = list_llama_cpp_models()
    selected = next((item for item in models if item["id"] == normalized_id), None)
    if selected is None:
        raise FileNotFoundError(f"Unknown GGUF model id: {normalized_id}")

    selected_path = Path(str(selected["path"])).resolve()
    if selected_path.suffix.lower() != ".gguf" or not selected_path.exists():
        raise FileNotFoundError(str(selected_path))

    current_path = get_llama_cpp_model_path().resolve()
    if selected_path != current_path:
        stop_llama_server(force=True)

    LLAMA_MODEL_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLAMA_MODEL_SELECTION_PATH.write_text(
        json.dumps({"name": selected["name"], "path": str(selected_path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    os.environ["LLAMA_CPP_MODEL"] = str(selected["name"])
    os.environ["LLAMA_CPP_MODEL_PATH"] = str(selected_path)
    return get_current_llama_cpp_model()


def get_llama_cpp_bin() -> Path:
    configured = os.environ.get("LLAMA_CPP_BIN")
    if configured:
        return Path(configured).expanduser()

    candidates = [
        RUNTIME_DIR / "llama.cpp" / "build" / "bin" / "llama-server",
        RUNTIME_DIR / "llama.cpp" / "build" / "bin" / "Release" / "llama-server",
        RUNTIME_DIR / "llama.cpp" / "build" / "bin" / "llama-server.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def is_llama_server_running() -> bool:
    with _lock:
        return _is_live_process(_llama_process)


def ensure_llama_server_running() -> None:
    """Start llama-server in the background and wait for /v1/models readiness."""
    global _llama_process

    with _lock:
        if _active_engine == "OCR_RUNNING":
            raise EngineBusyError("Cannot start llama-server while OCR is running")

        if _is_live_process(_llama_process):
            _wait_for_llama_server_ready()
            return

        if _llama_process is not None:
            _reap_process(_llama_process)
            _llama_process = None

        bin_path = get_llama_cpp_bin()
        model_path = get_llama_cpp_model_path()
        if not bin_path.exists():
            raise FileNotFoundError(
                f"llama-server not found at {bin_path}. Run scripts/ensure_llama_cpp_wsl.sh first "
                "or set LLAMA_CPP_BIN."
            )
        if not model_path.exists():
            raise FileNotFoundError(
                f"Qwen GGUF model not found at {model_path}. Run scripts/ensure_llama_cpp_wsl.sh first "
                "or set LLAMA_CPP_MODEL_PATH."
            )

        host, port = _host_port_from_base_url(get_llama_cpp_base_url())
        cmd = [
            str(bin_path),
            "-m",
            str(model_path),
            "--alias",
            get_llama_cpp_model(),
            "-c",
            str(int(os.environ.get("LLAMA_CPP_CTX_SIZE", str(DEFAULT_LLAMA_CPP_CTX_SIZE)))),
            "-t",
            str(int(os.environ.get("LLAMA_CPP_THREADS", str(DEFAULT_LLAMA_CPP_THREADS)))),
            "--host",
            host,
            "--port",
            str(port),
        ]
        flash_attn_mode = _llama_flash_attn_mode()
        if flash_attn_mode:
            cmd.extend(["--flash-attn", flash_attn_mode])

        log_path = RUNTIME_DIR / "logs" / "llama-server.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log_file:
            _llama_process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **_new_process_group_kwargs(),
            )

        try:
            _wait_for_llama_server_ready()
        except Exception:
            stop_llama_server(force=True)
            raise


def stop_llama_server(*, force: bool = False) -> None:
    """Terminate the managed llama-server and wait until the process is reaped."""
    global _llama_process

    with _lock:
        if _active_engine == "LLM_RUNNING" and not force:
            raise EngineBusyError("Cannot stop llama-server while an LLM request is active")
        process = _llama_process
        _llama_process = None

    if process is None:
        return
    _terminate_process_group(process, grace_seconds=float(os.environ.get("LLAMA_CPP_STOP_GRACE_SECONDS", "5")))


@contextmanager
def llm_request_guard() -> Iterator[None]:
    global _active_engine

    with _lock:
        if _active_engine != "IDLE":
            raise EngineBusyError(f"LLM request blocked because {_active_engine} is active")
        _active_engine = "LLM_RUNNING"
    try:
        yield
    finally:
        with _lock:
            _active_engine = "IDLE"


def create_resource_token(task_id: str, resource: EngineState) -> str:
    if resource in {"IDLE", "LLM_RUNNING"}:
        raise ValueError("resource token can only be created for external engines")
    token = uuid4().hex
    with _lock:
        _resource_tokens[token] = {"task_id": task_id, "resource": resource, "granted": False}
    return token


def request_runtime_resource(
    *,
    token: str,
    resource: EngineState,
    task_id: str,
    pid: int | None = None,
    reason: str = "",
) -> dict[str, Any]:
    _record_runtime_event(
        task_id,
        "RESOURCE_REQUESTED",
        "资源中断请求",
        f"{resource} requested by pid={pid or 'unknown'}; {reason}".strip(),
        {"resource": resource, "pid": pid, "reason": reason},
    )
    with _lock:
        record = _resource_tokens.get(token)
        if not record or record.get("task_id") != task_id or record.get("resource") != resource:
            raise PermissionError("invalid resource token")
        if _active_engine not in {"IDLE", resource}:
            raise EngineBusyError(f"Cannot grant {resource}; {_active_engine} is active")

    stop_llama_server(force=True)
    _record_runtime_event(
        task_id,
        "LLAMA_SERVER_STOPPED",
        "llama-server 已让出资源",
        "收到 OCR 中断请求后，已停止受控 llama-server。",
        {"resource": resource, "pid": pid},
    )

    with _lock:
        if _active_engine not in {"IDLE", resource}:
            raise EngineBusyError(f"Cannot grant {resource}; {_active_engine} is active")
        _set_active_engine(resource)
        record = _resource_tokens[token]
        record.update({"granted": True, "pid": pid, "reason": reason, "granted_at": time.time()})
    _record_runtime_event(
        task_id,
        "RESOURCE_GRANTED",
        "资源已授予",
        f"{resource} 已进入运行状态。",
        {"resource": resource, "pid": pid, "active_engine": get_active_engine()},
    )
    return {"ok": True, "granted": True, "resource": resource, "active_engine": get_active_engine()}


def release_runtime_resource(*, token: str, task_id: str | None = None, resource: EngineState | None = None) -> dict[str, Any]:
    with _lock:
        record = _resource_tokens.pop(token, None)
        if record is None:
            return {"ok": True, "released": False, "active_engine": _active_engine}
        if task_id is not None and record.get("task_id") != task_id:
            raise PermissionError("resource token does not belong to task")
        expected_resource = resource or record.get("resource")
        if _active_engine == expected_resource:
            _set_active_engine("IDLE")
        active_engine = _active_engine
    _record_runtime_event(
        str(record.get("task_id") or task_id or ""),
        "RESOURCE_RELEASED",
        "资源已释放",
        f"{expected_resource} 已释放，重型资源状态回到 {active_engine}。",
        {"resource": expected_resource, "active_engine": active_engine},
    )
    return {"ok": True, "released": True, "active_engine": active_engine}


def run_ocr_blocking(
    command: Sequence[str],
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout_seconds: float,
    log_path: Path,
    restart_llama: bool,
    token: str | None = None,
    task_id: str | None = None,
) -> ManagedProcessResult:
    """Run OCR as an interruptible external process.

    The child process must request OCR_RUNNING through the local callback before
    importing/loading OCR models, then release it before exit.
    """
    result: ManagedProcessResult | None = None
    try:
        result = run_interruptible_process(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
        return result
    finally:
        if token:
            release_runtime_resource(token=token, task_id=task_id, resource="OCR_RUNNING")
        if restart_llama:
            ensure_llama_server_running()


def run_interruptible_process(
    command: Sequence[str],
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout_seconds: float,
    log_path: Path,
) -> ManagedProcessResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd or PROJECT_ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **_new_process_group_kwargs(),
            )

        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process, grace_seconds=5)
            tail = _read_tail(log_path)
            raise ManagedProcessError(
                f"Process timed out after {timeout_seconds} seconds: {' '.join(command)}",
                returncode=None,
                log_path=log_path,
                log_tail=tail,
            ) from exc

        tail = _read_tail(log_path)
        if returncode != 0:
            raise ManagedProcessError(
                f"Process exited with code {returncode}: {' '.join(command)}",
                returncode=returncode,
                log_path=log_path,
                log_tail=tail,
            )
        return ManagedProcessResult(tuple(command), returncode, log_path, tail)
    finally:
        if process is not None and _is_live_process(process):
            _terminate_process_group(process, grace_seconds=5)


def run_exclusive_process(
    command: Sequence[str],
    *,
    engine_state: EngineState,
    cwd: Path | None,
    env: dict[str, str],
    timeout_seconds: float,
    log_path: Path,
) -> ManagedProcessResult:
    global _active_engine

    if engine_state == "IDLE":
        raise ValueError("engine_state must not be IDLE")

    with _lock:
        if _active_engine != "IDLE":
            raise EngineBusyError(f"Cannot start {engine_state}; {_active_engine} is active")
        _active_engine = engine_state

    log_path.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd or PROJECT_ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **_new_process_group_kwargs(),
            )

        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process, grace_seconds=5)
            tail = _read_tail(log_path)
            raise ManagedProcessError(
                f"Process timed out after {timeout_seconds} seconds: {' '.join(command)}",
                returncode=None,
                log_path=log_path,
                log_tail=tail,
            ) from exc

        tail = _read_tail(log_path)
        if returncode != 0:
            raise ManagedProcessError(
                f"Process exited with code {returncode}: {' '.join(command)}",
                returncode=returncode,
                log_path=log_path,
                log_tail=tail,
            )
        return ManagedProcessResult(tuple(command), returncode, log_path, tail)
    finally:
        if process is not None and _is_live_process(process):
            _terminate_process_group(process, grace_seconds=5)
        with _lock:
            _active_engine = "IDLE"


def cleanup_managed_processes() -> None:
    stop_llama_server(force=True)


def _set_active_engine(state: EngineState) -> None:
    global _active_engine
    _active_engine = state


def _wait_for_llama_server_ready() -> None:
    base_url = get_llama_cpp_base_url()
    url = f"{base_url}/models"
    timeout = float(os.environ.get("LLAMA_CPP_READY_TIMEOUT_SECONDS", "60"))
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.ok:
                return
            last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        except Exception as exc:  # noqa: BLE001 - readiness polling must tolerate startup races
            last_error = exc
        time.sleep(0.5)

    raise TimeoutError(f"llama-server did not become ready at {url}: {last_error}")


def _host_port_from_base_url(base_url: str) -> tuple[str, int]:
    # Avoid importing urllib in hot paths; the expected URL is simple and local.
    without_scheme = base_url.split("://", 1)[-1]
    host_port = without_scheme.split("/", 1)[0]
    if ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        return host, int(port_text)
    return host_port, 80


def _new_process_group_kwargs() -> dict[str, object]:
    if os.name == "posix":
        return {"start_new_session": True}
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": creationflags} if creationflags else {}


def _terminate_process_group(process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
    if not _is_live_process(process):
        _reap_process(process)
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


def _is_live_process(process: subprocess.Popen[bytes] | None) -> bool:
    return process is not None and process.poll() is None


def _reap_process(process: subprocess.Popen[bytes]) -> None:
    try:
        process.wait(timeout=0)
    except subprocess.TimeoutExpired:
        pass


def _read_tail(path: Path, *, max_bytes: int = 4096) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes), os.SEEK_SET)
        return handle.read().decode("utf-8", errors="replace")


def _load_selected_llama_model() -> dict[str, Any] | None:
    if not LLAMA_MODEL_SELECTION_PATH.exists():
        return None
    try:
        payload = json.loads(LLAMA_MODEL_SELECTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    path = str(payload.get("path") or "").strip()
    if not path:
        return None
    return payload


def _llama_model_search_dirs() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("LLAMA_CPP_MODEL_DIRS", "")
    for item in configured.split(os.pathsep):
        if item.strip():
            candidates.append(Path(item).expanduser())

    candidates.extend(
        [
            get_llama_cpp_model_path().expanduser().parent,
            PROJECT_ROOT,
            PROJECT_ROOT / "models",
            PROJECT_ROOT.parent,
            RUNTIME_DIR / "models",
            RUNTIME_DIR,
        ]
    )

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _model_info(path: Path, *, selected: bool) -> LlamaCppModelInfo:
    resolved = path.resolve()
    try:
        size_bytes = resolved.stat().st_size
    except OSError:
        size_bytes = 0
    return LlamaCppModelInfo(
        id=hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12],
        name=resolved.stem,
        path=str(resolved),
        size_bytes=size_bytes,
        selected=selected,
    )


def _record_runtime_event(
    task_id: str,
    event_type: str,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if not task_id:
        return
    try:
        from . import task_store

        task_store.add_event(
            task_id,
            event_type,
            title,
            message,
            {"active_engine": get_active_engine(), **(payload or {})},
        )
    except Exception:
        return


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _llama_flash_attn_mode() -> str | None:
    value = os.environ.get("LLAMA_CPP_FLASH_ATTN")
    if value is None or not value.strip():
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return "on"
    if normalized in {"0", "false", "no", "off"}:
        return "off"
    if normalized == "auto":
        return "auto"
    raise ValueError("LLAMA_CPP_FLASH_ATTN must be one of: 1/0, true/false, on/off, auto")


atexit.register(cleanup_managed_processes)
