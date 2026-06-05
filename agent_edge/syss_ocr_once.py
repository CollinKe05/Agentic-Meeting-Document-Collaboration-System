from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from .syss_ocr_runner import run_syss_ocr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SYSS OCR once without Agent runtime callbacks.")
    parser.add_argument("-i", "--input", required=True, help="PDF/image path to parse.")
    parser.add_argument("-o", "--output-root", required=True, help="Directory for OCR artifacts.")
    parser.add_argument(
        "--syss-project-dir",
        default="",
        help="External syss project root, e.g. /home/sunrise/syss/syss_f16yolo.",
    )
    parser.add_argument("--syss-import-name", default="", help="Optional package import name for SYSS_PROJECT_DIR.")
    args = parser.parse_args(argv)

    if args.syss_project_dir:
        os.environ["SYSS_PROJECT_DIR"] = str(Path(args.syss_project_dir).expanduser())
    if args.syss_import_name:
        os.environ["SYSS_IMPORT_NAME"] = args.syss_import_name

    input_path = Path(args.input).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / f"{input_path.stem}_ocr_result.json"

    try:
        result = run_syss_ocr(input_path=input_path, output_root=output_root)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        error = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        result_path.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(error["traceback"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
