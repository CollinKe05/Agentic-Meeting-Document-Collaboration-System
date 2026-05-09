# 本地技能索引

可用技能：

- `read_file_skill.md`：学习如何安全读取本地文本文件。
- `local_tool_skill.md`：学习可用的本地 dummy 工具。

约束：

- 所有技能文件必须位于 `skills/` 目录下。
- 不允许路径穿越，例如 `../secret.txt`。
- 不允许调用云端 API。
- 工具执行必须通过 `execute_local_action(action, action_input)`。
