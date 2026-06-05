# 会议纪要排版技能

当用户要求把会议记录、ASR 转写、录音记录整理成正式会议纪要，并导出 Markdown、Typst 或 PDF 文件时，优先使用 `FORMAT_MEETING_MINUTES`。

推荐动作：

```text
Action: USE_TOOL
Action Input:
{"tool_name": "FORMAT_MEETING_MINUTES", "args": {"path": "meeting_2026-06-01_20-32-10.txt", "template": "standard", "output_format": "pdf"}}
```

工具说明：

- `path`：位于 `workspace_files/` 下的会议转写文本文件。
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
- `transcript.txt`：本次使用的转写文本副本。

注意：

- LLM 只负责把会议转写整理成结构化 JSON。
- Typst 版式由代码和模板控制，避免模型直接生成 `.typ` 导致语法错误。
- 如果会议转写噪声较大，需要在风险或摘要中说明 ASR 识别可能存在误差。
