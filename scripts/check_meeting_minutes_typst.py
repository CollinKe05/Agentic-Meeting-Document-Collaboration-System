from __future__ import annotations

import json
import shutil

from agent_edge.meeting_formatter import format_meeting_minutes


def main() -> int:
    transcript = """开始时间：2026-06-04 21:30:00
[21:30:01] 讨论 OCR 改 BPU 推理。
[21:30:20] 会议纪要需要导出 Typst 和 PDF。
[21:31:00] 待办是接入模板并验证端侧部署。
"""
    result = format_meeting_minutes(
        {
            "transcript": transcript,
            "title": "会议纪要 Typst 自检",
            "template": "standard",
            "output_format": "pdf",
            "use_llm": False,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    typst_ok = bool(result.get("typst", {}).get("ok"))
    if not typst_ok:
        print("\nWARN: Typst PDF 未生成。请检查 TYPST_BIN、.runtime/bin/typst 或 PATH。")
        print(f"which typst: {shutil.which('typst')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
