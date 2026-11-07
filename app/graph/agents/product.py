"""商品 Agent —— 处理商品查询、库存、规格等意图。

只读工具：查询商品/库存；写工具：补货申请（需授权）。
"""
from __future__ import annotations

from typing import Any

from app.llm.mock import get_llm
from app.storage.store import get_storage


def product_node(state: dict[str, Any]) -> dict[str, Any]:
    """商品 Agent 节点：查询商品事实并生成可解释摘要。"""
    storage = get_storage()
    llm = get_llm()

    product_id = state.get("product_id", "")
    facts: dict[str, Any] = {}

    if product_id:
        product = storage.get_product(product_id)
        if product:
            facts = {
                "商品": product["name"],
                "价格": f"¥{product['price']}",
                "库存": product["stock"],
                "类目": product["category"],
                "规格": product["specs"],
            }
        else:
            facts = {"提示": f"商品 {product_id} 不存在"}
    else:
        products = storage.list_products()
        facts = {"商品数量": len(products), "商品列表": [p["name"] for p in products]}

    summary = llm.generate_summary("product", facts)

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["product"] = summary

    return {
        "agent_outputs": agent_outputs,
        "product_id": product_id,
    }
