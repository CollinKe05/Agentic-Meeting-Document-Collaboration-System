from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run OCR_pc after requesting Agent runtime resources.")
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
                "reason": f"OCR parse {input_path.name}",
            },
        )
        resource_granted = True

        ocr_project_dir = Path(os.environ.get("OCR_PC_PROJECT_DIR", PROJECT_ROOT / "OCR_pc" / "OCR_pc")).resolve()
        sys.path.insert(0, str(ocr_project_dir))

        from core.markdown import to_markdown_v2  # type: ignore[import-not-found]
        from core.pdf2img import pdf_to_images  # type: ignore[import-not-found]
        from core.pipeline_onnx import process_image  # type: ignore[import-not-found]

        page_dir = output_root / f"{input_path.stem}_pages"
        all_blocks: list[dict[str, Any]] = []
        suffix = input_path.suffix.lower()
        if suffix == ".pdf":
            page_paths = pdf_to_images(str(input_path), output_dir=str(page_dir))
            for page_index, page_path in enumerate(page_paths, start=1):
                for block in process_image(page_path):
                    normalized = dict(block)
                    normalized["page"] = page_index
                    all_blocks.append(normalized)
        elif suffix in IMAGE_SUFFIXES:
            for block in process_image(str(input_path)):
                normalized = dict(block)
                normalized["page"] = 1
                all_blocks.append(normalized)
        else:
            raise ValueError(f"Unsupported OCR document type: {input_path.suffix}")

        markdown = to_markdown_v2(all_blocks)
        markdown_path = output_root / f"{input_path.stem}.md"
        blocks_path = output_root / f"{input_path.stem}_blocks.json"
        content_v2_path = output_root / f"{input_path.stem}_content_list_v2.json"

        markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
        blocks_path.write_text(json.dumps(all_blocks, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        content_v2_path.write_text(
            json.dumps(_to_content_list_v2(all_blocks), ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

        result = {
            "ok": True,
            "input_path": str(input_path),
            "output_root": str(output_root),
            "markdown_path": str(markdown_path),
            "blocks_json_path": str(blocks_path),
            "content_list_v2_path": str(content_v2_path),
            "images_dir": str(page_dir) if page_dir.exists() else None,
            "block_count": len(all_blocks),
            "markdown_preview": markdown[:6000],
        }
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


def _to_content_list_v2(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        text = "".join(str(item) for item in block.get("text", []))
        content.append(
            {
                "id": index,
                "type": block.get("type", "text"),
                "page": block.get("page", 1),
                "text": text,
                "bbox": block.get("box") or block.get("bbox"),
            }
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
