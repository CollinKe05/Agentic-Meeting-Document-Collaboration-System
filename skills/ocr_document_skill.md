# OCR / SYSS 文档解析技能

当用户要求解析 PDF、图片、扫描件、截图、拍照文档，或明确提到 OCR/PaddleOCR/SYSS 时，优先使用本地 OCR 工具。

工具名为了兼容旧规划器仍保留为：

```text
PARSE_DOCUMENT_WITH_OCR_PC
```

但默认后端已经切换为项目内 `sys_core.syss`：

- BPU 可用时：优先使用 RDK BPU OCR。
- BPU 不可用时：回退到 ONNX/CPU OCR。
- 版面模型默认从项目根目录 `models/` 读取。
- `yolov8n_layout_general6.onnx` 与 DocLayout 1024 模型由 `LayoutAnalyzer` 自动适配。

推荐动作：

```text
Action: USE_TOOL
Action Input:
{"tool_name": "PARSE_DOCUMENT_WITH_OCR_PC", "args": {"path": "uploads/sample.pdf"}}
```

支持格式：

- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.tif`
- `.tiff`
- `.webp`

不适合 OCR 的情况：

- `.txt`、`.md`、`.json`、`.py`、`.csv` 等文本文件应使用 `SAFE_READ_TEXT_FILE`。
- `.docx`、`.pptx`、`.xlsx` 暂不直接解析；需要先转成 PDF 或图片。

OCR 解析输出：

- `markdown_path`：OCR 后生成的 Markdown 原文。
- `blocks_json_path`：版面块、OCR 文本和坐标。
- `content_list_v2_path`：简化结构化内容列表。
- `images_dir`：PDF 页面图片目录，图片输入时可为空。
- `block_count`：识别出的版面块数量。
- `text_count`：识别出的文本框数量。
- `markdown_preview`：给 Agent 展示用的 Markdown 预览。
- `log_path`：OCR 子进程日志。

资源规则：

- OCR 是重型工具，运行前会向 Agent 申请 `OCR_RUNNING`。
- Agent 收到申请后会暂停 `llama-server`，让 OCR 独占资源。
- OCR 完成并释放资源后，Agent 才能重新调用 LLM。
- 不要让 OCR 和 LLM 推理同时执行。

配置规则：

- 默认无需设置 `SYSS_PROJECT_DIR`，项目内 `sys_core.syss` 就是主 OCR 后端。
- 如需临时测试外部流水线，可设置 `SYSS_PROJECT_DIR` 和 `SYSS_IMPORT_NAME`。
- 板端 BPU runtime 可通过 `SYSS_BPU_RUNTIME_DIR` 指定。
- BPU 模型可通过 `SYSS_BPU_DET`、`SYSS_BPU_REC`、`SYSS_BPU_DICT` 覆盖。
- YOLO 版面模型可通过 `SYSS_YOLO_MODEL` 覆盖。

常见请求：

- “解析这个 PDF”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “识别图片里的文字”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “把扫描件转 Markdown”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “根据上一次 OCR 结果回答”：调用 `READ_LAST_OCR_RESULT`。

## OCR Summary Export

OCR 解析和 OCR 总结导出是两个动作。

- `PARSE_DOCUMENT_WITH_OCR_PC` 只负责解析源文档，写出 Markdown、JSON、图片等原文产物。
- 它可以返回粗略预览，但不要在 OCR 解析阶段生成正式总结文档。
- 当用户只是要求“总结 OCR 结果/概括刚才 OCR 内容”时，只做短摘要，不生成 JSON/Markdown/Typst/PDF 报告文件。
- 当用户明确要求“生成 JSON/Markdown/Typst/PDF”、“格式化 OCR 总结文档”、“导出 OCR 报告”时，使用 `EXPORT_OCR_SUMMARY`。
- `EXPORT_OCR_SUMMARY` 必须基于 OCR Markdown 原文生成，而不是基于粗略预览生成。
- `EXPORT_OCR_SUMMARY` 必须绑定明确的 OCR Markdown；当前任务没有 OCR 产物时应提示用户选择 OCR 文档，不应自动套用上一份文件。
- 当输入路径已经是 `ocr_outputs/*.md`，并且用户要求生成 OCR 总结、报告、Markdown、Typst、PDF 或 metadata JSON 时，禁止先调用 `SAFE_READ_TEXT_FILE` / 普通文件读取工具。
- `EXPORT_OCR_SUMMARY` 自己负责读取 OCR Markdown、压缩 evidence、调用 LLM 和生成导出文件；不要在它之前读取整份 OCR Markdown，否则大文件会触发 65536 bytes 限制。
- OCR 解析完成后的即时回复只报告产物路径、文本块数量和很短的预览；正式总结报告只能由 `EXPORT_OCR_SUMMARY` 生成。

推荐动作：

```text
Action: USE_TOOL
Action Input:
{"tool_name": "EXPORT_OCR_SUMMARY", "args": {"path": "ocr_outputs/example.md", "template": "standard", "output_format": "pdf"}}
```

最终回答需要包含：

- `json_path`
- `markdown_path`
- `typ_path`
- `pdf_path`
- `source_markdown_path`
- `source_copy_path`

如果未安装 Typst，说明 PDF 没生成，但 JSON、Markdown、Typst 文件已经生成。
