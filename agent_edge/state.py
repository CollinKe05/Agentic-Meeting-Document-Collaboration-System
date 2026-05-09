from __future__ import annotations

from typing import List

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 全局状态。

    plan 是待执行队列。
    past_steps 是 Reflexion 记忆，存放 (Action, Observation)。
    current_response 存放当前节点给外部的可读响应，也携带内部路由标记。
    """

    user_input: str
    plan: List[dict]
    past_steps: List[tuple]
    current_response: str
