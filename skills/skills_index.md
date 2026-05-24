# 本地技能索引

可用技能：

- `read_file_skill.md`：学习如何安全读取本地文本文件。
- `local_tool_skill.md`：学习当前可用的本地工具，包括 MinerU 文档解析。

约束：

- 技能文件必须位于 `skills/` 目录。
- 禁止路径穿越，例如 `../secret.txt`。
- Agent 核心运行时不调用云端 API。
- 重型引擎互斥：LLM 推理和 MinerU 解析不能同时运行。
