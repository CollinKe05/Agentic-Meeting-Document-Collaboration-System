# OCR/PaddleOCR 文档解析技能

当用户要求解析 PDF、图片、扫描件、截图、拍照文档，或明确提到 OCR/PaddleOCR 时，优先使用 `PARSE_DOCUMENT_WITH_OCR_PC`。

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

不适合使用 OCR 的情况：

- `.txt`、`.md`、`.json`、`.py`、`.csv` 等文本文件应使用 `SAFE_READ_TEXT_FILE`。
- `.docx`、`.pptx`、`.xlsx` 第一版暂不直接支持，后续需要先转 PDF 或图片。

工具输出：

- `markdown_path`：OCR 后生成的 Markdown。
- `blocks_json_path`：OCR 文本块与坐标。
- `content_list_v2_path`：简化结构化内容列表。
- `images_dir`：PDF 页图目录，图片输入可能为空。
- `block_count`：识别出的文本块数量。
- `markdown_preview`：给 LLM 总结使用的 Markdown 预览。
- `log_path`：OCR 子进程日志。

资源规则：

- OCR 是重型工具，运行前会向 Agent 发出资源中断请求。
- Agent 收到请求后会停止 `llama-server`，让出内存。
- OCR 完成并释放资源后，Agent 才能重新调用 LLM 总结 Markdown。
- 不要让 OCR 与 LLM 推理同时执行。

后端配置：

- 默认工具名仍是 `PARSE_DOCUMENT_WITH_OCR_PC`。
- 板端 RDK BPU OCR 流水线设 `AGENT_OCR_BACKEND=syss`。
- 若使用板端独立 syss 流水线，设 `SYSS_PROJECT_DIR=/home/sunrise/syss/syss_f16yolo`。
- BPU 模型路径用 `SYSS_BPU_RUNTIME_DIR`、`SYSS_BPU_DET`、`SYSS_BPU_REC`、`SYSS_BPU_DICT` 配置。
- DocLayout-YOLO 第一版仍走 CPU ONNX，路径用 `SYSS_YOLO_MODEL` 配置。

用户常见请求与处理：

- “解析这个 PDF”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “识别图片里的文字”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “把扫描件转 Markdown”：调用 `PARSE_DOCUMENT_WITH_OCR_PC`。
- “总结 OCR 结果”：先调用 OCR，再基于 `markdown_preview` 或 `markdown_path` 总结。
- “根据上一次 OCR 结果回答”：调用 `READ_LAST_OCR_RESULT` 读取最近 OCR Markdown，再基于内容回答。
