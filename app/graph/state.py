"""内部共享状态定义（LangGraph state + checkpoint）。

设计要点：
- 内部 4 个 Agent 共享同一份 state，实现「内部紧耦合」。
- checkpoint 字段承载内部 Checkpoint（供恢复/重放）。
- external_task_ids 承载外部委派任务 ID（与内部 Checkpoint 分离，
  避免内外状态互相污染——这是 P19 的核心护栏设计）。
"""
from __future__ import annotations

from typing import Any, TypedDict


class InternalState(TypedDict, total=False):
    # 用户请求
    user_request: str

    # 意图路由结果：product / order / service / marketing
    intent: str

    # 当前处理的业务对象 ID
    product_id: str
    order_id: str

    # 各 Agent 产出的中间结果
    agent_outputs: dict[str, Any]

    # 内部 Checkpoint（内部可信状态）
    checkpoint: dict[str, Any]

    # 外部委派任务 ID 映射（partner -> task_id），与内部状态分离
    external_task_ids: dict[str, str]

    # 最终汇总结果
    final_summary: str

    # 是否需要外部数据（触发 A2A 委派）
    need_external: bool

    # 外部委派目标合作伙伴（supplier / logistics）
    partner: str
