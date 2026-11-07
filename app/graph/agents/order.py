"""订单 Agent —— 处理订单查询、物流、售后等意图。

只读工具：查询订单/物流；写工具：改单/退款（需授权）。
"""
from __future__ import annotations

from typing import Any

from app.llm.mock import get_llm
from app.storage.store import get_storage


def order_node(state: dict[str, Any]) -> dict[str, Any]:
    """订单 Agent 节点：查询订单事实并生成可解释摘要。"""
    storage = get_storage()
    llm = get_llm()

    order_id = state.get("order_id", "")
    facts: dict[str, Any] = {}

    if order_id:
        order = storage.get_order(order_id)
        if order:
            facts = {
                "订单号": order["id"],
                "商品ID": order["product_id"],
                "数量": order["qty"],
                "状态": order["status"],
                "物流": order["logistics"] or "暂无物流信息",
                "收货人": order["user_name"],
            }
        else:
            facts = {"提示": f"订单 {order_id} 不存在"}
    else:
        facts = {"提示": "请提供订单号以便查询"}

    summary = llm.generate_summary("order", facts)

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["order"] = summary

    return {
        "agent_outputs": agent_outputs,
        "order_id": order_id,
    }
