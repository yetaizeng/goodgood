"""客服 Agent —— 处理咨询、投诉、售后政策等意图。"""
from __future__ import annotations

from typing import Any

from app.llm.mock import get_llm
from app.storage.store import get_storage


def service_node(state: dict[str, Any]) -> dict[str, Any]:
    """客服 Agent 节点：基于政策与订单状态生成答复。"""
    llm = get_llm()
    storage = get_storage()

    request = state.get("user_request", "")
    facts: dict[str, Any] = {
        "客服类型": "售后咨询",
        "处理原则": "查单须鉴权；退款和承诺须有权人员确认",
    }

    # 若请求中带订单号，尝试关联订单
    order_id = state.get("order_id", "")
    if order_id:
        order = storage.get_order(order_id)
        if order:
            facts["关联订单"] = order["id"]
            facts["订单状态"] = order["status"]
        else:
            facts["关联订单"] = f"{order_id}（未找到）"

    summary = llm.generate_summary("service", facts)

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["service"] = summary

    return {"agent_outputs": agent_outputs}
