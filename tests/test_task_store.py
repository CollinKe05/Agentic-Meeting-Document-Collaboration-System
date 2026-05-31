from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_edge import task_store


class TaskStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "tasks.sqlite3"
        self.env = mock.patch.dict(os.environ, {"AGENT_DB_PATH": str(self.db_path)}, clear=False)
        self.env.start()
        task_store.reset_initialized_for_tests()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()
        task_store.reset_initialized_for_tests()

    def test_create_task_and_events_are_persisted(self) -> None:
        task = task_store.create_task(
            "task-1",
            prompt="请总结文件",
            backend="llama_cpp",
            attachments=[{"path": "uploads/demo.txt"}],
        )
        event = task_store.add_event("task-1", "PLAN_REQUESTED", "开始规划", "ok")
        updated = task_store.update_task("task-1", status="completed", result="完成")

        self.assertEqual(task["status"], "queued")
        self.assertEqual(updated["result"], "完成")
        self.assertEqual(event["type"], "PLAN_REQUESTED")
        self.assertEqual(task_store.list_events("task-1")[0]["message"], "ok")
        self.assertEqual(task_store.list_tasks()[0]["attachments"][0]["path"], "uploads/demo.txt")

    def test_record_artifact(self) -> None:
        artifact = task_store.record_artifact(
            "file-1",
            task_id=None,
            kind="upload",
            path="uploads/a.txt",
            name="a.txt",
            metadata={"bytes": 3},
        )

        self.assertEqual(artifact["path"], "uploads/a.txt")
        self.assertEqual(artifact["metadata"]["bytes"], 3)

    def test_latest_artifact_by_kind(self) -> None:
        task_store.record_artifact("upload-1", task_id=None, kind="upload", path="uploads/a.txt", name="a.txt")
        latest_ocr = task_store.record_artifact("ocr-1", task_id="task-1", kind="ocr_result", path="ocr_outputs/a.md", name="a.md")

        self.assertEqual(task_store.latest_artifact(kind="ocr_result"), latest_ocr)
        self.assertEqual(task_store.latest_artifact(kind="upload")["id"], "upload-1")


if __name__ == "__main__":
    unittest.main()
