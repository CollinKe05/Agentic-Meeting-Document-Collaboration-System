from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
import urllib.request
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SYSS OCR after requesting Agent runtime resources.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--callback-url", required=True)
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / f"{input_path.stem}_ocr_result.json"

    resource_granted = False
    try:
        _post_json(
            f"{args.callback_url.rstrip('/')}/request",
            {
                "token": args.token,
                "resource": "OCR_RUNNING",
                "task_id": args.task_id,
                "pid": os.getpid(),
                "reason": f"SYSS OCR parse {input_path.name}",
            },
        )
        resource_granted = True

        result = run_syss_ocr(input_path=input_path, output_root=output_root)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        return 0
    except Exception as exc:  # noqa: BLE001 - runner boundary
        error = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        result_path.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(error["traceback"], file=sys.stderr)
        return 1
    finally:
        if resource_granted:
            try:
                _post_json(
                    f"{args.callback_url.rstrip('/')}/release",
                    {"token": args.token, "resource": "OCR_RUNNING", "task_id": args.task_id, "pid": os.getpid()},
                )
            except Exception as exc:  # noqa: BLE001 - best-effort release
                print(f"resource release failed: {exc}", file=sys.stderr)


def run_syss_ocr(*, input_path: Path, output_root: Path) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    syss_runtime = _load_syss_runtime()
    cfg = syss_runtime.config_cls()
    pipeline_result = syss_runtime.pipeline_cls(cfg).run(str(input_path), str(output_root))

    markdown_path = Path(str(pipeline_result["markdown"]))
    sorted_path = Path(str(pipeline_result["sorted_json"]))
    merged_path = Path(str(pipeline_result["merged_json"]))
    sorted_data = _read_json(sorted_path)
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")

    blocks_path = output_root / f"{input_path.stem}_blocks.json"
    content_v2_path = output_root / f"{input_path.stem}_content_list_v2.json"
    blocks_path.write_text(
        json.dumps(sorted_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    content_v2_path.write_text(
        json.dumps(_to_content_list_v2(sorted_data), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    return {
        "ok": True,
        "backend": "syss",
        "syss_import": syss_runtime.import_name,
        "syss_project_dir": str(syss_runtime.project_dir) if syss_runtime.project_dir is not None else None,
        "ocr_backend": _normalize_ocr_backend(str(pipeline_result.get("ocr_backend") or "")),
        "ocr_overlap": pipeline_result.get("ocr_overlap"),
        "layout_backend": pipeline_result.get("layout_backend"),
        "sorter_backend": pipeline_result.get("sorter_backend"),
        "input_path": str(input_path),
        "output_root": str(output_root),
        "markdown_path": str(markdown_path),
        "blocks_json_path": str(blocks_path),
        "content_list_v2_path": str(content_v2_path),
        "images_dir": pipeline_result.get("images_dir"),
        "checkpoint_dir": pipeline_result.get("checkpoint_dir"),
        "merged_json_path": str(merged_path),
        "sorted_json_path": str(sorted_path),
        "block_count": pipeline_result.get("block_count") or _count_blocks(sorted_data),
        "text_count": pipeline_result.get("text_count"),
        "pages": pipeline_result.get("pages"),
        "elapsed": pipeline_result.get("elapsed"),
        "markdown_preview": markdown[:6000],
    }


class SyssRuntime:
    def __init__(self, *, config_cls: type, pipeline_cls: type, import_name: str, project_dir: Path | None) -> None:
        self.config_cls = config_cls
        self.pipeline_cls = pipeline_cls
        self.import_name = import_name
        self.project_dir = project_dir


def _load_syss_runtime() -> SyssRuntime:
    configured = os.environ.get("SYSS_PROJECT_DIR", "").strip()
    if configured:
        return _load_external_syss_runtime(Path(configured).expanduser().resolve())

    from sys_core.syss.config import SystemConfig
    from sys_core.syss.pipeline import DocumentPipeline

    return SyssRuntime(
        config_cls=SystemConfig,
        pipeline_cls=DocumentPipeline,
        import_name="sys_core.syss",
        project_dir=None,
    )


def _load_external_syss_runtime(project_dir: Path) -> SyssRuntime:
    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError(f"SYSS_PROJECT_DIR not found: {project_dir}")
    if not (project_dir / "pipeline.py").exists():
        raise FileNotFoundError(f"SYSS_PROJECT_DIR does not contain pipeline.py: {project_dir}")

    package_name = os.environ.get("SYSS_IMPORT_NAME", "").strip() or project_dir.name
    parent = str(project_dir.parent)
    root = str(project_dir)

    errors: list[str] = []
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        config_mod = importlib.import_module(f"{package_name}.config")
        pipeline_mod = importlib.import_module(f"{package_name}.pipeline")
        return SyssRuntime(
            config_cls=config_mod.SystemConfig,
            pipeline_cls=pipeline_mod.DocumentPipeline,
            import_name=package_name,
            project_dir=project_dir,
        )
    except Exception as exc:  # noqa: BLE001 - fallback supports top-level syss projects
        errors.append(f"{package_name} package import failed: {type(exc).__name__}: {exc}")

    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        config_mod = importlib.import_module("config")
        pipeline_mod = importlib.import_module("pipeline")
        return SyssRuntime(
            config_cls=config_mod.SystemConfig,
            pipeline_cls=pipeline_mod.DocumentPipeline,
            import_name="top_level_syss",
            project_dir=project_dir,
        )
    except Exception as exc:  # noqa: BLE001 - include both attempts in error
        errors.append(f"top-level import failed: {type(exc).__name__}: {exc}")
        raise ImportError("; ".join(errors)) from exc


def _to_content_list_v2(sorted_data: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    index = 1
    for page in sorted_data.get("pages", []):
        page_index = int(page.get("page_index", 0)) + 1
        for block in page.get("blocks", []):
            block_info = block.get("block_info", {})
            text = " ".join(
                str(tb.get("transcription", "")).strip()
                for tb in block.get("contained_text_boxes", [])
                if not tb.get("is_virtual") and str(tb.get("transcription", "")).strip()
            ).strip()
            content.append(
                {
                    "id": index,
                    "type": block_info.get("class_name", "text"),
                    "page": page_index,
                    "text": text,
                    "bbox": block_info.get("bbox"),
                    "reading_order": block_info.get("textbox_reading_order_median"),
                    "is_virtual_text": block_info.get("is_virtual_text", False),
                }
            )
            index += 1
    return content


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - local callback only
        data = json.loads(response.read().decode("utf-8") or "{}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"resource request failed: {url}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _count_blocks(sorted_data: dict[str, Any]) -> int:
    return sum(len(page.get("blocks", [])) for page in sorted_data.get("pages", []))


def _normalize_ocr_backend(name: str) -> str:
    lowered = name.lower()
    if "rdkbpu" in lowered:
        return "rdk_bpu"
    if "bpu" in lowered:
        return "bpu"
    if "onnx" in lowered:
        return "onnx_cpu"
    return lowered or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
