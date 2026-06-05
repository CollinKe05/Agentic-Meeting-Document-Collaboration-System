# 会议纪要排版技能

当用户要求把会议记录、ASR 转写、录音记录整理成正式会议纪要，并导出 Markdown、Typst 或 PDF 文件时，优先使用 `FORMAT_MEETING_MINUTES`。

推荐动作：

```text
Action: USE_TOOL
Action Input:
{"tool_name": "FORMAT_MEETING_MINUTES", "args": {"path": "meeting_records/meeting_2026-06-01_20-32-10.txt", "template": "standard", "output_format": "pdf"}}
```

工具说明：

- `path`：位于 `workspace_files/` 下的会议转写文本文件。会议记录结束后会自动归档到 `workspace_files/meeting_records/`。
- `template`：默认 `standard`，对应 `templates/meeting_minutes/standard.typ`。
- `output_format`：默认尝试生成 `pdf`；如果系统没有安装 `typst`，仍会生成 `.typ`、`.md` 和 `.json`。

输出文件会写入：

```text
workspace_files/meeting_outputs/
```

结果包含：

- `minutes.json`：结构化会议纪要数据。
- `minutes.md`：Markdown 会议纪要。
- `minutes.typ`：Typst 排版源码。
- `minutes.pdf`：如果系统安装了 `typst`，自动编译生成 PDF。
- 桌面 PDF：如果能找到桌面目录，PDF 会额外复制一份到桌面。
- `transcript.txt`：本次使用的转写文本副本。

注意：

- LLM 只负责把会议转写整理成结构化 JSON。
- LLM 应分部分生成概览、议题结论、待办风险，不要一次性粗略生成全文。
- `key_points`、主要议题讨论点、风险/待确认事项应尽量拆成至少 5 条；信息密度高时自然增加条数，信息不足时说明缺口。
- Typst 版式由代码和模板控制，避免模型直接生成 `.typ` 导致语法错误。
- 如果会议转写噪声较大，需要在风险或摘要中说明 ASR 识别可能存在误差。
