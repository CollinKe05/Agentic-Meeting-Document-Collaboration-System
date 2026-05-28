from __future__ import annotations

import json
import os
import re
import time
import uuid
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import task_store
from .event_agent import features, start_task, wait_for_task
from .heavy_runtime import (
    cleanup_managed_processes,
    get_active_engine,
    is_llama_server_running,
    release_runtime_resource,
    request_runtime_resource,
)
from .paths import PROJECT_ROOT, SKILLS_DIR, WORKSPACE_DIR, ensure_demo_assets, read_limited_text, safe_child_path, write_limited_text


UI_DIR = Path(__file__).resolve().parent / "ui"
MAX_UPLOAD_BYTES = int(os.environ.get("AGENT_UI_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
SSE_SLEEP_SECONDS = 0.35
SSE_MAX_SECONDS = int(os.environ.get("AGENT_SSE_MAX_SECONDS", "3600"))
LLAMA_CPP_BACKEND = "llama_cpp"


def main() -> int:
    ensure_demo_assets()
    task_store.ensure_schema()
    host = os.environ.get("AGENT_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_UI_PORT", "7860"))
    os.environ.setdefault("AGENT_RESOURCE_CALLBACK_URL", f"http://127.0.0.1:{port}/api/runtime/resource")
    server = ThreadingHTTPServer((host, port), AgentUIHandler)
    print(f"Agent UI 已启动：http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("正在关闭 Agent UI...")
    finally:
        from .meeting_asr import cleanup_asr_processes

        cleanup_asr_processes()
        cleanup_managed_processes()
        server.server_close()
    return 0


class AgentUIHandler(BaseHTTPRequestHandler):
    server_version = "AgentUI/0.2"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib callback name
        return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_file(_ui_index_path(), "text/html; charset=utf-8")
            return
        if path in {"/tailwind.min.js", "/agent-ui-runtime.js"}:
            self._send_file(safe_child_path(PROJECT_ROOT, path.lstrip("/")), _content_type(Path(path)))
            return
        if path == "/api/features":
            self._send_json({"ok": True, "features": _features()})
            return
        if path == "/api/system/status":
            self._send_json(
                {
                    "ok": True,
                    "active_engine": get_active_engine(),
                    "llama_server_running": is_llama_server_running(),
                }
            )
            return
        if path == "/api/meeting/status":
            from .meeting_asr import meeting_status

            self._send_json({"ok": True, "meeting": meeting_status()})
            return
        if path == "/api/voice-input/status":
            from .meeting_asr import voice_input_status

            self._send_json({"ok": True, "voice_input": voice_input_status()})
            return
        if path == "/api/tasks":
            limit = int(parse_qs(parsed.query).get("limit", ["50"])[0])
            self._send_json({"ok": True, "tasks": task_store.list_tasks(limit=limit)})
            return
        if match := re.fullmatch(r"/api/tasks/([A-Za-z0-9_-]+)", path):
            task = task_store.get_task(match.group(1))
            if not task:
                self._send_json({"ok": False, "error": "任务不存在"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"ok": True, "task": task, "events": task_store.list_events(task["id"])})
            return
        if match := re.fullmatch(r"/api/tasks/([A-Za-z0-9_-]+)/events", path):
            query = parse_qs(parsed.query)
            after_id = int(query.get("after_id", ["0"])[0])
            self._stream_task_events(match.group(1), after_id=after_id)
            return
        if path == "/api/skills":
            self._handle_get_skills(parsed)
            return
        if path.startswith("/assets/"):
            rel = path.replace("/assets/", "", 1)
            asset_path = safe_child_path(UI_DIR, rel)
            self._send_file(asset_path, _content_type(asset_path))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/tasks":
            self._handle_create_task()
            return
        if path == "/api/chat":
            self._handle_legacy_chat()
            return
        if path == "/api/upload":
            self._handle_upload()
            return
        if path == "/api/skills":
            self._handle_save_skill()
            return
        if path == "/api/runtime/resource/request":
            self._handle_resource_request()
            return
        if path == "/api/runtime/resource/release":
            self._handle_resource_release()
            return
        if path == "/api/meeting/start":
            self._handle_meeting_start()
            return
        if path == "/api/meeting/stop":
            self._handle_meeting_stop()
            return
        if path == "/api/meeting/summary":
            self._handle_meeting_summary()
            return
        if path == "/api/voice-input/start":
            self._handle_voice_input_start()
            return
        if path == "/api/voice-input/stop":
            self._handle_voice_input_stop()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/api/skills":
            self._handle_save_skill()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_create_task(self) -> None:
        try:
            payload = self._read_json()
            prompt = str(payload.get("prompt", "")).strip()
            backend = _normalize_backend(payload.get("backend"))
            attachments = payload.get("attachments") or []
            if not isinstance(attachments, list):
                raise ValueError("attachments 必须是数组")
            task = start_task(prompt, backend=backend, attachments=attachments)
            self._send_json({"ok": True, "task": task, "task_id": task["id"]}, HTTPStatus.ACCEPTED)
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_legacy_chat(self) -> None:
        try:
            payload = self._read_json()
            prompt = str(payload.get("prompt", "")).strip()
            backend = _normalize_backend(payload.get("backend"))
            task = start_task(prompt, backend=backend, attachments=payload.get("attachments") or [])
            finished = wait_for_task(task["id"], timeout_seconds=float(payload.get("timeout_seconds", 180)))
            if not finished or finished["status"] != "completed":
                raise TimeoutError(f"任务未在同步等待窗口内完成：{task['id']}")
            self._send_json(
                {
                    "ok": True,
                    "task_id": task["id"],
                    "response": finished.get("result") or "",
                    "steps": _events_to_steps(task_store.list_events(task["id"])),
                    "task": finished,
                }
            )
        except Exception as exc:  # noqa: BLE001 - compatibility boundary
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_upload(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("没有收到上传内容")
            if length > MAX_UPLOAD_BYTES:
                raise ValueError(f"上传内容过大，限制为 {MAX_UPLOAD_BYTES} bytes")

            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            raw = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
            message = BytesParser(policy=default).parsebytes(raw)
            if not message.is_multipart():
                raise ValueError("上传请求必须是 multipart/form-data")

            saved: list[dict[str, Any]] = []
            upload_dir = WORKSPACE_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            for part in message.iter_parts():
                filename = part.get_filename()
                if not filename:
                    continue
                file_id = uuid.uuid4().hex[:12]
                safe_name = _safe_filename(filename)
                path = upload_dir / f"{file_id}-{safe_name}"
                data = part.get_payload(decode=True) or b""
                path.write_bytes(data)
                rel_path = path.relative_to(WORKSPACE_DIR).as_posix()
                artifact = task_store.record_artifact(
                    file_id,
                    task_id=None,
                    kind="upload",
                    path=rel_path,
                    name=safe_name,
                    metadata={"bytes": len(data), "content_type": part.get_content_type()},
                )
                saved.append(
                    {
                        "file_id": file_id,
                        "name": safe_name,
                        "path": rel_path,
                        "size": len(data),
                        "type": part.get_content_type(),
                        "artifact": artifact,
                    }
                )

            if not saved:
                raise ValueError("没有找到文件字段")
            self._send_json({"ok": True, "files": saved})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_get_skills(self, parsed: Any) -> None:
        query = parse_qs(parsed.query)
        name = query.get("name", [""])[0]
        try:
            if name:
                path = safe_child_path(SKILLS_DIR, name, expected_suffix=".md")
                self._send_json({"ok": True, "name": path.name, "content": read_limited_text(path)})
                return
            skills = sorted(path.name for path in SKILLS_DIR.glob("*.md") if path.is_file())
            self._send_json({"ok": True, "skills": skills})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_save_skill(self) -> None:
        try:
            payload = self._read_json()
            name = str(payload.get("name", "")).strip()
            content = str(payload.get("content", ""))
            if not name:
                raise ValueError("skill 文件名不能为空")
            if not name.endswith(".md"):
                name = f"{name}.md"
            path = safe_child_path(SKILLS_DIR, name, expected_suffix=".md")
            write_limited_text(path, content, overwrite=True)
            self._send_json({"ok": True, "name": path.name})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_resource_request(self) -> None:
        try:
            payload = self._read_json()
            result = request_runtime_resource(
                token=str(payload.get("token", "")),
                resource=str(payload.get("resource", "")),  # type: ignore[arg-type]
                task_id=str(payload.get("task_id", "")),
                pid=int(payload["pid"]) if payload.get("pid") is not None else None,
                reason=str(payload.get("reason", "")),
            )
            self._send_json(result)
        except Exception as exc:  # noqa: BLE001 - internal API boundary
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.BAD_REQUEST)

    def _handle_resource_release(self) -> None:
        try:
            payload = self._read_json()
            result = release_runtime_resource(
                token=str(payload.get("token", "")),
                task_id=str(payload.get("task_id", "")) or None,
                resource=str(payload.get("resource", "")) or None,  # type: ignore[arg-type]
            )
            self._send_json(result)
        except Exception as exc:  # noqa: BLE001 - internal API boundary
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.BAD_REQUEST)

    def _handle_meeting_start(self) -> None:
        try:
            from .meeting_asr import start_meeting

            self._send_json({"ok": True, "meeting": start_meeting()})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_meeting_stop(self) -> None:
        try:
            from .meeting_asr import stop_meeting

            self._send_json({"ok": True, "meeting": stop_meeting()})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_meeting_summary(self) -> None:
        try:
            from .meeting_asr import meeting_summary_prompt

            prompt = meeting_summary_prompt()
            task = start_task(prompt, backend=LLAMA_CPP_BACKEND, attachments=[])
            self._send_json({"ok": True, "task": task, "task_id": task["id"]}, HTTPStatus.ACCEPTED)
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_voice_input_start(self) -> None:
        try:
            from .meeting_asr import start_voice_input

            self._send_json({"ok": True, "voice_input": start_voice_input()})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_voice_input_stop(self) -> None:
        try:
            from .meeting_asr import stop_voice_input

            self._send_json({"ok": True, "voice_input": stop_voice_input()})
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _stream_task_events(self, task_id: str, *, after_id: int) -> None:
        task = task_store.get_task(task_id)
        if not task:
            self._send_json({"ok": False, "error": "任务不存在"}, HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_id = after_id
        started = time.monotonic()
        while time.monotonic() - started < SSE_MAX_SECONDS:
            events = task_store.list_events(task_id, after_id=last_id, limit=50)
            for event in events:
                last_id = int(event["id"])
                self._write_sse("agent_event", event, event_id=last_id)

            task = task_store.get_task(task_id)
            if task and task["status"] in task_store.TERMINAL_TASK_STATUSES:
                self._write_sse("task_state", {"task": task}, event_id=last_id + 1)
                return

            self._write_sse("heartbeat", {"task_id": task_id, "last_id": last_id})
            time.sleep(SSE_SLEEP_SECONDS)

    def _write_sse(self, event: str, payload: dict[str, Any], event_id: int | None = None) -> None:
        try:
            if event_id is not None:
                self.wfile.write(f"id: {event_id}\n".encode("utf-8"))
            self.wfile.write(f"event: {event}\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON object")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _features() -> list[dict[str, Any]]:
    return features()


def _normalize_backend(value: Any) -> str:
    backend = str(value or LLAMA_CPP_BACKEND).strip()
    if backend != LLAMA_CPP_BACKEND:
        raise ValueError("当前项目只支持 llama.cpp 后端")
    return LLAMA_CPP_BACKEND


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "upload.bin"
    name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name)
    return name[:120]


def _events_to_steps(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for event in events:
        if event["type"] not in {"TOOL_REQUESTED", "OCR_REQUIRED"}:
            continue
        payload = event.get("payload", {})
        steps.append(
            {
                "index": str(payload.get("index", len(steps) + 1)),
                "action": str(payload.get("action", event["title"])),
                "input": str(payload.get("action_input", "")),
                "observation": str(event.get("message", "")),
            }
        )
    return steps


def _ui_index_path() -> Path:
    root_index = PROJECT_ROOT / "index.html"
    if root_index.exists():
        return root_index
    return UI_DIR / "index.html"


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        return f"image/{suffix.lstrip('.')}"
    return "application/octet-stream"


if __name__ == "__main__":
    raise SystemExit(main())
