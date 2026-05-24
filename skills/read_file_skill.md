# 安全读取文件技能

当用户要求读取本地文本文件时，优先使用 `SAFE_READ_TEXT_FILE`。

推荐动作：

```text
Action: USE_TOOL
Action Input:
{"tool_name": "SAFE_READ_TEXT_FILE", "args": {"path": "demo_input.txt"}}
```

安全策略：

- 只能读取 `workspace_files/` 目录下的文件。
- 禁止绝对路径。
- 禁止 `../` 路径穿越。
- 文件大小受 `AGENT_MAX_LOCAL_FILE_BYTES` 限制。

如果用户没有指定文件，默认读取：

```text
demo_input.txt
```
