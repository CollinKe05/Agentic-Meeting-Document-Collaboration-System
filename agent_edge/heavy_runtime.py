from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Sequence

import requests

from .paths import PROJECT_ROOT


EngineState = Literal["IDLE", "LLM_RUNNING", "MINERU_RUNNING", "ASR_STREAMING", "OCR_RUNNING"]

RUNTIME_DIR = Path(os.environ.get("AGENT_RUNTIME_DIR", PROJECT_ROOT / ".runtime")).expanduser()
DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_LLAMA_CPP_MODEL = "qwen2.5-1.5b-instruct-q4_k_m"
DEFAULT_LLAMA_CPP_MODEL_PATH = RUNTIME_DIR / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_LLAMA_CPP_THREADS = 4
DEFAULT_LLAMA_CPP_CTX_SIZE = 4096

_lock = threading.RLock()
_active_engine: EngineState = "IDLE"
_llama_process: subprocess.Popen[bytes] | None = None


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


def get_active_engine() -> EngineState:
    with _lock:
        return _active_engine


def get_llama_cpp_base_url() -> str:
    return os.environ.get("LLAMA_CPP_BASE_URL", DEFAULT_LLAMA_CPP_BASE_URL).rstrip("/")


def get_llama_cpp_model() -> str:
    return os.environ.get("LLAMA_CPP_MODEL", DEFAULT_LLAMA_CPP_MODEL)


def get_llama_cpp_model_path() -> Path:
    return Path(os.environ.get("LLAMA_CPP_MODEL_PATH", str(DEFAULT_LLAMA_CPP_MODEL_PATH))).expanduser()


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
        if _active_engine == "MINERU_RUNNING":
            raise EngineBusyError("Cannot start llama-server while MinerU is running")

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
        if _env_flag("LLAMA_CPP_FLASH_ATTN", default=False):
            cmd.append("--flash-attn")

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


def run_mineru_blocking(
    command: Sequence[str],
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout_seconds: float,
    log_path: Path,
    restart_llama: bool,
) -> ManagedProcessResult:
    """Run MinerU as the only active heavy engine, restarting llama-server afterward."""
    stop_llama_server()
    result: ManagedProcessResult | None = None
    try:
        result = run_exclusive_process(
            command,
            engine_state="MINERU_RUNNING",
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
        return result
    finally:
        if restart_llama:
            ensure_llama_server_running()


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


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


atexit.register(cleanup_managed_processes)
