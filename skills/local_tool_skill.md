# 本地工具技能

可用 dummy 工具：

- `LOCAL_ECHO`：回显文本。
- `COUNT_TEXT_CHARS`：统计文本字符数。
- `LIST_SKILLS`：列出 `skills/` 下的 markdown 文件。
- `SAFE_READ_TEXT_FILE`：读取 `workspace_files/` 下的文本文件。
- `SAFE_WRITE_TEXT_FILE`：写入 `workspace_files/` 下的文本文件。

所有工具输入格式：

```json
{
  "tool_name": "TOOL_NAME",
  "args": {}
}
```
