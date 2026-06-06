# 本地日程管理技能

用于管理 `todo_rdk/data/tasks.db` 中的日程和待办事项。

推荐动作：

Action: USE_TOOL
Action Input:
{"tool_name": "APPLY_TODO_INSTRUCTION", "args": {"instruction": "提醒我明天下午3点开会"}}

可用工具：

- `LIST_TODO_TASKS`：列出或按 query 搜索日程。
- `ADD_TODO_TASK`：新增日程，字段包括 `title`、`description`、`priority`、`category`、`due_date`。
- `UPDATE_TODO_TASK`：按 `id` 或 `query/title` 修改日程字段。
- `COMPLETE_TODO_TASK`：按 `id` 或 `query/title` 标记完成。
- `DELETE_TODO_TASK`：按 `id` 或 `query/title` 删除日程。
- `APPLY_TODO_INSTRUCTION`：解析自然语言日程指令，安全地添加、修改、完成或删除日程。

约束：

- `priority` 只能是 `高`、`中`、`低`，默认 `中`。
- `due_date` 使用 `YYYY-MM-DD HH:MM:SS`。
- 当日期、时间或目标任务不明确时，不要猜测写库，应该返回澄清信息。
- 多条日程同时匹配时，不要自动修改或删除，应该要求用户指定更明确的标题或 id。
