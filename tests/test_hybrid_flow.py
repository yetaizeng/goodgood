"""核心闭环测试 —— 真实运行验证。

覆盖三条闭环：
1. 内部 LangGraph 编排（意图路由 + 共享 state + checkpoint）
2. A2A 外部委派（验签 + 幂等 + 回执）
3. 护栏（外部 Agent 无内部写权限）
"""
from __future__ import annotations

import pytest

from app.graph.orchestrator import get_graph
from app.interop.a2a_delegate import delegate_to_partner
from app.storage.store import get_storage


@pytest.fixture(autouse=True)
def _fresh_graph():
    """每个测试用独立 thread_id，避免 checkpoint 串扰。"""
    import uuid

    return str(uuid.uuid4())


# ----------------------------------------------------------------------
# 1. 内部 LangGraph 编排闭环
# ----------------------------------------------------------------------
def test_intent_routing_product():
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-product-1"}}
    result = graph.invoke({"user_request": "查一下商品P100的价格和库存"}, config=config)
    assert result["intent"] == "product"
    assert result["checkpoint"]["intent"] == "product"
    assert "product" in result["agent_outputs"]


def test_intent_routing_order():
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-order-1"}}
    result = graph.invoke({"user_request": "订单A123的物流到哪了"}, config=config)
    assert result["intent"] == "order"
    assert result["order_id"] == "A123"
    assert "order" in result["agent_outputs"]


def test_intent_routing_service():
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-service-1"}}
    result = graph.invoke({"user_request": "我要投诉商品质量问题"}, config=config)
    assert result["intent"] == "service"
    assert "service" in result["agent_outputs"]


def test_intent_routing_marketing():
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-marketing-1"}}
    result = graph.invoke({"user_request": "帮我写一个P100的促销文案"}, config=config)
    assert result["intent"] == "marketing"
    assert "marketing" in result["agent_outputs"]


def test_shared_state_and_final_summary():
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-final-1"}}
    result = graph.invoke({"user_request": "查一下商品P100的库存"}, config=config)
    assert result["final_summary"] != ""
    assert "product" in result["final_summary"]


def test_external_partner_routing():
    """外部委派目标正确路由：物流->logistics，补货->supplier。"""
    graph = get_graph()
    # 物流关键词 -> logistics
    r1 = graph.invoke({"user_request": "订单A123的物流到哪了"}, config={"configurable": {"thread_id": "t-log"}})
    assert r1["need_external"] is True
    assert r1["partner"] == "logistics"

    # 补货关键词 -> supplier
    r2 = graph.invoke({"user_request": "商品P100缺货了，帮我补货"}, config={"configurable": {"thread_id": "t-sup"}})
    assert r2["need_external"] is True
    assert r2["partner"] == "supplier"


# ----------------------------------------------------------------------
# 2. A2A 外部委派闭环
# ----------------------------------------------------------------------
def test_a2a_supplier_stock_query():
    result = delegate_to_partner("supplier", {"action": "query_stock", "product_id": "P100"})
    assert result["status"] == "accepted"
    assert "stock" in result["receipt"]
    assert result["signature"]


def test_a2a_supplier_replenish():
    result = delegate_to_partner("supplier", {"action": "replenish", "product_id": "P100", "qty": 10})
    assert result["status"] == "accepted"
    assert result["receipt"]["status"] == "replenished"


def test_a2a_logistics_query():
    result = delegate_to_partner("logistics", {"action": "query_logistics", "order_id": "A123"})
    assert result["status"] == "accepted"
    assert "logistics" in result["receipt"]


def test_a2a_idempotency():
    """幂等：相同 task_id 重复委派返回同一结果。"""
    task = {"action": "query_stock", "product_id": "P100", "task_id": "fixed-task-123"}
    r1 = delegate_to_partner("supplier", task)
    r2 = delegate_to_partner("supplier", task)
    assert r1["task_id"] == r2["task_id"] == "fixed-task-123"


def test_a2a_unknown_partner_rejected():
    result = delegate_to_partner("unknown_partner", {"action": "x"})
    assert result["status"] == "rejected"


# ----------------------------------------------------------------------
# 3. 护栏闭环（外部 Agent 无内部写权限）
# ----------------------------------------------------------------------
def test_guard_external_agent_no_write_permission():
    storage = get_storage()
    with pytest.raises(PermissionError):
        # 外部主体尝试写内部库，必须被护栏拒绝
        storage.update_order_status("A123", "已退款", operator="external-supplier")


def test_guard_internal_operator_can_write():
    storage = get_storage()
    # 内部授权人可写
    storage.update_order_status("A123", "已退款", operator="internal-operator")
    order = storage.get_order("A123")
    assert order["status"] == "已退款"


def test_guard_replenish_requires_authorization():
    storage = get_storage()
    with pytest.raises(PermissionError):
        storage.create_replenish_task("P100", 10, operator="external-logistics")
