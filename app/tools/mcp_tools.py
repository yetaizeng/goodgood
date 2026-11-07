"""MCP 工具层 —— 将内部业务能力封装为标准工具（读写分级）。

设计原则（P19 护栏）：
- 只读工具：查询商品/订单/评论，任何调用方可安全使用。
- 写工具：补货申请/改单，需人工确认（operator 必须为内部授权人）。
- 外部 Agent 无内部写权限：写工具的 operator 校验会拒绝外部主体。
"""
from __future__ import annotations

from typing import Optional

from app.storage.store import get_storage


def query_product(product_id: str) -> dict:
    """只读工具：查询商品信息。"""
    storage = get_storage()
    product = storage.get_product(product_id)
    if not product:
        return {"error": f"商品 {product_id} 不存在"}
    return {"id": product["id"], "name": product["name"], "price": product["price"], "stock": product["stock"]}


def list_products(category: Optional[str] = None) -> list[dict]:
    """只读工具：列出商品。"""
    storage = get_storage()
    return storage.list_products(category)


def query_order(order_id: str) -> dict:
    """只读工具：查询订单信息。"""
    storage = get_storage()
    order = storage.get_order(order_id)
    if not order:
        return {"error": f"订单 {order_id} 不存在"}
    return {
        "id": order["id"],
        "product_id": order["product_id"],
        "qty": order["qty"],
        "status": order["status"],
        "logistics": order["logistics"],
    }


def get_reviews(product_id: str) -> list[dict]:
    """只读工具：查询商品评价。"""
    storage = get_storage()
    return storage.get_reviews(product_id)


def submit_replenish(product_id: str, qty: int, operator: str = "internal-operator") -> dict:
    """受控写工具：提交补货申请（需内部授权人确认）。

    护栏：operator 必须是内部授权人，否则抛出 PermissionError。
    """
    storage = get_storage()
    try:
        task_id = storage.create_replenish_task(product_id, qty, operator)
        return {"status": "submitted", "task_id": task_id, "note": "待内部负责人确认"}
    except PermissionError as e:
        return {"status": "rejected", "error": str(e)}


def update_order_status(order_id: str, status: str, operator: str = "internal-operator") -> dict:
    """受控写工具：更新订单状态（需内部授权人确认）。"""
    storage = get_storage()
    try:
        storage.update_order_status(order_id, status, operator)
        return {"status": "updated", "order_id": order_id, "new_status": status}
    except PermissionError as e:
        return {"status": "rejected", "error": str(e)}
