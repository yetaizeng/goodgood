"""营销 Agent —— 处理营销、促销、文案等意图。

事实约束生成：基于商品事实 + 模板生成草稿，不补写不存在的事实。
"""
from __future__ import annotations

from typing import Any

from app.llm.mock import get_llm
from app.storage.store import get_storage


def marketing_node(state: dict[str, Any]) -> dict[str, Any]:
    """营销 Agent 节点：生成营销文案草稿（事实约束）。"""
    llm = get_llm()
    storage = get_storage()

    product_id = state.get("product_id", "")
    facts: dict[str, Any] = {}

    template = "{name} 限时优惠，仅需 ¥{price}！{specs}，{category}优选。"
    if product_id:
        product = storage.get_product(product_id)
        if product:
            draft = llm.generate_draft(
                template,
                {
                    "name": product["name"],
                    "price": product["price"],
                    "specs": product["specs"],
                    "category": product["category"],
                },
            )
            facts = {"营销文案草稿": draft, "商品": product["name"]}
        else:
            facts = {"提示": f"商品 {product_id} 不存在，无法生成文案"}
    else:
        products = storage.list_products()
        drafts = []
        for p in products[:2]:  # 最多生成 2 条示例
            drafts.append(
                llm.generate_draft(
                    template,
                    {
                        "name": p["name"],
                        "price": p["price"],
                        "specs": p["specs"],
                        "category": p["category"],
                    },
                )
            )
        facts = {"营销文案草稿": drafts}

    summary = llm.generate_summary("marketing", facts)

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["marketing"] = summary

    return {"agent_outputs": agent_outputs}
