"""外部合作伙伴 Agent 测试替身（供应商 / 物流）。

这些是「松耦合」外部 Agent 的本地模拟端点：
- 它们不共享内部 state/权限（外部 Agent 输出视为不可信输入）。
- 返回回执带签名，供内部验签。
- 支持幂等键、超时模拟。

真实场景中这些是远端 A2A Agent，通过 Agent Card 发现并委派。
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any


def _sign(task_id: str, payload: dict) -> str:
    """模拟回执签名（HMAC 风格，确定性）。"""
    raw = task_id + str(sorted(payload.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class SupplierAgentStub:
    """供应商 Agent 替身：处理库存查询 / 补货委派。"""

    name = "supplier"

    def __init__(self) -> None:
        self._stock = {"P100": 50, "P101": 30, "P102": 200}

    def handle_task(self, task: dict[str, Any], timeout: float = 5.0) -> dict:
        """处理委派任务，返回带签名的回执。"""
        task_id = task.get("task_id") or str(uuid.uuid4())
        action = task.get("action", "query_stock")
        product_id = task.get("product_id", "")

        if action == "query_stock":
            stock = self._stock.get(product_id, 0)
            payload = {"stock": stock, "checked_at": time.time()}
        elif action == "replenish":
            qty = task.get("qty", 0)
            self._stock[product_id] = self._stock.get(product_id, 0) + qty
            payload = {"status": "replenished", "eta": "3d", "added": qty}
        else:
            payload = {"status": "unknown_action", "action": action}

        return {
            "task_id": task_id,
            "partner": self.name,
            "status": "accepted",
            "receipt": payload,
            "signature": _sign(task_id, payload),
        }


class LogisticsAgentStub:
    """物流 Agent 替身：处理配送 / 物流查询委派。"""

    name = "logistics"

    def __init__(self) -> None:
        self._shipments: dict[str, str] = {
            "A123": "SF1234567890 在途，预计2日内送达",
            "A124": "待发货，预计明日发出",
        }

    def handle_task(self, task: dict[str, Any], timeout: float = 5.0) -> dict:
        task_id = task.get("task_id") or str(uuid.uuid4())
        action = task.get("action", "query_logistics")
        order_id = task.get("order_id", "")

        if action == "query_logistics":
            info = self._shipments.get(order_id, "无该订单物流信息")
            payload = {"logistics": info, "checked_at": time.time()}
        elif action == "dispatch":
            payload = {"status": "dispatched", "courier": "SF", "eta": "1d"}
        else:
            payload = {"status": "unknown_action", "action": action}

        return {
            "task_id": task_id,
            "partner": self.name,
            "status": "accepted",
            "receipt": payload,
            "signature": _sign(task_id, payload),
        }
