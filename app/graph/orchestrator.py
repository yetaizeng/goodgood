"""内部 Orchestrator —— LangGraph 状态图编排。

职责：
- 意图路由（内部紧耦合：4 个 Agent 共享 state）
- 条件边（按 intent 分发到对应 Agent）
- Checkpoint 管理（内部可信状态）
- 标记是否需要外部数据（触发 A2A 委派）

架构亮点：内部紧耦合 + 外部松耦合的分层设计。
"""
from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import InternalState
from app.graph.agents.product import product_node
from app.graph.agents.order import order_node
from app.graph.agents.service import service_node
from app.graph.agents.marketing import marketing_node
from app.llm.mock import get_llm

# 需要触发外部 A2A 委派的关键词（库存/补货 -> 供应商；物流/配送 -> 物流）
_EXTERNAL_KEYWORDS = {
    "supplier": ("补货", "库存查询", "供应商", "缺货"),
    "logistics": ("物流", "配送", "快递", "发货"),
}


def _orchestrator_node(state: InternalState) -> dict[str, Any]:
    """Orchestrator 节点：意图分类 + 业务对象抽取 + 外部需求判断。"""
    llm = get_llm()
    request = state.get("user_request", "")

    intent = llm.classify_intent(request)

    # 从请求中抽取业务对象 ID（简单规则：匹配 P/A 前缀的 ID）
    product_id = _extract_id(request, "P")
    order_id = _extract_id(request, "A")

    # 判断是否需要外部数据
    need_external = False
    partner = ""
    for p_name, keywords in _EXTERNAL_KEYWORDS.items():
        if any(kw in request for kw in keywords):
            need_external = True
            partner = p_name
            break

    # 内部 Checkpoint（可信状态快照）
    checkpoint = {
        "intent": intent,
        "request": request,
        "product_id": product_id,
        "order_id": order_id,
    }

    return {
        "intent": intent,
        "product_id": product_id,
        "order_id": order_id,
        "checkpoint": checkpoint,
        "need_external": need_external,
        "partner": partner,
    }


def _extract_id(text: str, prefix: str) -> str:
    """从请求中抽取形如 P100 / A123 的业务对象 ID。"""
    import re

    m = re.search(rf"{prefix}\d+", text)
    return m.group(0) if m else ""


def _route_by_intent(state: InternalState) -> Literal["product", "order", "service", "marketing"]:
    """条件边：按意图路由到对应 Agent。"""
    return state.get("intent", "service")


def _finalize_node(state: InternalState) -> dict[str, Any]:
    """汇总节点：合并各 Agent 输出，生成最终结果。"""
    outputs = state.get("agent_outputs", {})
    parts = []
    for key in ("product", "order", "service", "marketing"):
        if key in outputs:
            parts.append(outputs[key])
    final_summary = "\n\n".join(parts) if parts else "（无 Agent 输出）"
    return {"final_summary": final_summary}


def build_graph():
    """构建内部编排状态图（含内存 checkpoint）。"""
    graph = StateGraph(InternalState)

    graph.add_node("orchestrator", _orchestrator_node)
    graph.add_node("product_agent", product_node)
    graph.add_node("order_agent", order_node)
    graph.add_node("service_agent", service_node)
    graph.add_node("marketing_agent", marketing_node)
    graph.add_node("finalize", _finalize_node)

    graph.set_entry_point("orchestrator")

    graph.add_conditional_edges(
        "orchestrator",
        _route_by_intent,
        {
            "product": "product_agent",
            "order": "order_agent",
            "service": "service_agent",
            "marketing": "marketing_agent",
        },
    )

    # 各 Agent 完成后统一进入汇总节点
    graph.add_edge("product_agent", "finalize")
    graph.add_edge("order_agent", "finalize")
    graph.add_edge("service_agent", "finalize")
    graph.add_edge("marketing_agent", "finalize")

    graph.add_edge("finalize", END)

    # 内存 checkpoint（内部可信状态持久化/重放）
    return graph.compile(checkpointer=MemorySaver())


# 模块级单例
_graph = build_graph()


def get_graph():
    return _graph
