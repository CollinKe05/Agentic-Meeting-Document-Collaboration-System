from __future__ import annotations

import os
import queue
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .event_agent import EVENT_ASR_SEGMENT_READY
from .paths import PROJECT_ROOT


@dataclass(frozen=True)
class PerceptionEvent:
    event_type: str
    priority: int
    payload: dict[str, Any]


class PerceptionQueue:
    """BPU 感知事件队列的轻量抽象。

    第一版用 Fake Adapter 验证调度语义；替换到 Sherpa-onnx 或 BPU OCR 时，
    保持 put/get 接口不变。
    """

    def __init__(self) -> None:
        self._queue: queue.PriorityQueue[tuple[int, str, PerceptionEvent]] = queue.PriorityQueue()

    def put(self, event: PerceptionEvent) -> None:
        self._queue.put((-event.priority, uuid.uuid4().hex, event))

    def get_nowait(self) -> PerceptionEvent | None:
        try:
            return self._queue.get_nowait()[2]
        except queue.Empty:
            return None


class FakeAsrAdapter:
    def __init__(self, events: PerceptionQueue) -> None:
        self.events = events

    def accept_text_segment(self, text: str, *, meeting_id: str = "default") -> PerceptionEvent:
        event = PerceptionEvent(
            event_type=EVENT_ASR_SEGMENT_READY,
            priority=100,
            payload={"meeting_id": meeting_id, "text": text},
        )
        self.events.put(event)
        return event


class FakeOcrAdapter:
    def parse_image(self, path: str) -> dict[str, Any]:
        return {
            "ok": True,
            "backend": "fake_ocr",
            "path": path,
            "markdown": f"![image]({path})\n\nFake OCR 尚未接入真实 BPU 模型。",
        }


def tmpfs_audio_dir() -> Path:
    preferred = Path(os.environ.get("AGENT_AUDIO_TMPFS_DIR", "/dev/shm/agent_audio"))
    if preferred.parent.exists() and os.access(preferred.parent, os.W_OK):
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    fallback = PROJECT_ROOT / ".runtime" / "dev_shm_fallback" / "agent_audio"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def delete_audio_chunk(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
