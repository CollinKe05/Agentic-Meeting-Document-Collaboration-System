# 本地工具技能

可用工具：

- `LOCAL_ECHO`：回显文本，适合做连通性测试。
- `COUNT_TEXT_CHARS`：统计文本字符数。
- `LIST_SKILLS`：列出 `skills/` 目录下的 Markdown 技能文件。
- `SAFE_READ_TEXT_FILE`：读取 `workspace_files/` 下的文本文件。
- `SAFE_WRITE_TEXT_FILE`：写入 `workspace_files/` 下的文本文件。
- `PARSE_DOCUMENT_WITH_OCR_PC`：使用 OCR/PaddleOCR 解析 PDF 或图片。
- `READ_LAST_OCR_RESULT`：读取最近一次 OCR 解析生成的 Markdown，用于追问和继续总结。

推荐技能文件：

- 读取文本文件前，学习 `read_file_skill.md`。
- 解析 PDF、图片、扫描件前，学习 `ocr_document_skill.md`。
- 处理会议记录、语音输入、会议总结前，学习 `asr_meeting_skill.md`。
- 用户说“上一次 OCR 结果”“刚才那个文档”“根据这个 PDF 回答”等追问时，使用 `READ_LAST_OCR_RESULT`。

通用约束：

- 只能访问 `workspace_files/` 与 `skills/` 允许范围内的文件。
- 禁止绝对路径和 `../` 路径穿越。
- OCR 与 LLM 推理互斥，OCR 前 Agent 会停止受控 `llama-server`。
- ASR/会议记录由 UI 或 Web API 控制，不是普通 `USE_TOOL` 工具。
