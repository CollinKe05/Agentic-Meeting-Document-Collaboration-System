# 本地技能索引

可用技能：

- `read_file_skill.md`：学习如何安全读取本地文本文件。
- `local_tool_skill.md`：学习当前可用的本地工具，包括 OCR、文件读写和会议纪要排版。
- `ocr_document_skill.md`：学习如何调用 OCR/PaddleOCR 解析 PDF、图片和扫描件。
- `asr_meeting_skill.md`：学习会议记录、实时转写、语音输入和会议总结流程。
- `meeting_minutes_skill.md`：学习如何把会议转写生成 Markdown、Typst 和 PDF 会议纪要文件。

约束：

- 技能文件必须位于 `skills/` 目录。
- 禁止路径穿越，例如 `../secret.txt`。
- Agent 核心运行时不调用云端 API。
- 重型引擎互斥：LLM 推理和 OCR 解析不能同时运行。
- ASR 第一版走本地 CPU；会议总结和会议纪要排版进入 LLM 队列。
