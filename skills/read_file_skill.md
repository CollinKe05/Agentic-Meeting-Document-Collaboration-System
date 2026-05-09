# 安全读取文件技能

当任务需要读取本地文本文件时，先使用这个技能。

推荐动作：

```text
Action: USE_TOOL
Action Input: {"tool_name": "SAFE_READ_TEXT_FILE", "args": {"path": "demo_input.txt"}}
```

安全策略：

- 只能读取 `workspace_files/` 目录下的文件。
- 使用 `pathlib.Path.resolve()` 规范化路径。
- 使用 `relative_to()` 校验目标路径没有逃逸出允许目录。
- 文件大小超过限制时拒绝读取。
