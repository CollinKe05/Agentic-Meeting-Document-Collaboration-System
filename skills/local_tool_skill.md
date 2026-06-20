# 本地工具技能

可用工具：

- `LOCAL_ECHO`：回显文本，适合做连通性测试。
- `COUNT_TEXT_CHARS`：统计文本字符数。
- `LIST_SKILLS`：列出 `skills/` 目录下的 Markdown 技能文件。
- `SAFE_READ_TEXT_FILE`：读取 `workspace_files/` 下的文本文件。
- `SAFE_WRITE_TEXT_FILE`：写入 `workspace_files/` 下的文本文件。
- `PARSE_DOCUMENT_WITH_OCR_PC`：兼容旧工具名，实际默认调用项目内 `sys_core.syss` OCR 流水线解析 PDF 或图片。
- `READ_LAST_OCR_RESULT`：读取最近一次 OCR 解析生成的 Markdown，用于追问和继续总结。
- `EXPORT_OCR_SUMMARY`：基于 OCR Markdown 原文生成 JSON、Markdown、Typst，并在安装 Typst 时生成 PDF。
- `FORMAT_MEETING_MINUTES`：把会议转写整理成结构化会议纪要，并生成 `.json`、`.md`、`.typ`，安装 Typst 时生成 `.pdf`。
- `LIST_TODO_TASKS`：列出或搜索本地日程。
- `ADD_TODO_TASK`：新增本地日程。
- `UPDATE_TODO_TASK`：修改本地日程。
- `COMPLETE_TODO_TASK`：标记本地日程完成。
- `DELETE_TODO_TASK`：删除本地日程。
- `APPLY_TODO_INSTRUCTION`：解析自然语言日程指令，例如“提醒我明天下午3点开会”。

推荐技能文件：

- 读取文本文件前，学习 `read_file_skill.md`。
- 解析 PDF、图片、扫描件前，学习 `ocr_document_skill.md`。
- 处理会议记录、语音输入、会议总结前，学习 `asr_meeting_skill.md`。
- 生成会议纪要排版文件、Typst 或 PDF 前，学习 `meeting_minutes_skill.md`。
- 用户只是说“总结 OCR 结果/概括刚才 OCR 内容”时，优先读取对应 OCR Markdown 并给短摘要，不生成报告文件。
- 只有用户明确要求“生成 OCR 总结文档/导出 OCR PDF/Markdown/Typst/生成报告/排版报告”时，才使用 `EXPORT_OCR_SUMMARY`。
- 如果用户已经选择或给出 `ocr_outputs/*.md`，并要求生成 OCR 报告、导出 Markdown/Typst/PDF/JSON，必须直接调用 `EXPORT_OCR_SUMMARY`，不要先调用 `SAFE_READ_TEXT_FILE`。
- `EXPORT_OCR_SUMMARY` 内部会读取和压缩 OCR Markdown；普通文件读取有 65536 bytes 限制，不能用于大 OCR Markdown 报告导出。
- 用户说“上一次 OCR 结果”“刚才那个文档”“根据这个 PDF 回答”等追问时，使用 `READ_LAST_OCR_RESULT`。
- 用户说“添加日程”“提醒我”“完成某个待办”“删除某个日程”“把日程改到某时间”时，学习 `todo_schedule_skill.md` 并使用日程工具。

通用约束：

- 只能访问 `workspace_files/` 与 `skills/` 允许范围内的文件。
- 禁止绝对路径和 `../` 路径穿越。
- OCR 与 LLM 推理互斥；OCR 前 Agent 会停止受控 `llama-server`。
- ASR/会议记录由 UI 或 Web API 控制；会议纪要排版可以通过 `FORMAT_MEETING_MINUTES` 处理已有 transcript。
- 日程工具只操作 `todo_rdk/data/tasks.db`，不修改 Agent 执行任务表。
