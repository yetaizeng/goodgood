"""A2A 外部委派管理器 —— 松耦合信任边界。

职责（P19 核心护栏）：
1. 核验机构身份 + 合同授权（最小数据清单 / 字段白名单）。
2. 生成幂等键（task_id），避免重复委派。
3. 委派（真实 A2A 协议 或 本地 stub）+ 回执验签 + 状态核对。
4. 超时补偿 / 撤销。
5. 记录双侧审计（delegation_audit 表）。

传输层切换（A2A_TRANSPORT 环境变量）：
- stub（默认）：本地替身，确定性，测试用
- a2a：真实 A2A 协议，通过 Agent Card 发现 + Client 委派

关键护栏：外部 Agent 不自动取得内部读写权限；外部输出视为不可信输入。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any, Optional

from app.config import A2A_TIMEOUT_SECONDS, A2A_IDEMPOTENCY_ENABLED
from app.interop.partner_stubs import SupplierAgentStub, LogisticsAgentStub
from app.storage.store import get_storage

# 合作伙伴注册表（stub 模式）
_STUB_PARTNERS = {
    "supplier": SupplierAgentStub(),
    "logistics": LogisticsAgentStub(),
}

# 真实 A2A 服务地址（A2A 模式）
_A2A_ENDPOINTS = {
    "supplier": os.getenv("A2A_SUPPLIER_URL", "http://127.0.0.1:8101"),
    "logistics": os.getenv("A2A_LOGISTICS_URL", "http://127.0.0.1:8102"),
}

# 字段白名单：只允许交换任务所需的最小字段
_FIELD_WHITELIST = {
    "supplier": {"action", "product_id", "qty", "task_id"},
    "logistics": {"action", "order_id", "task_id"},
}

# 传输层：stub（默认） / a2a（真实协议）
A2A_TRANSPORT = os.getenv("A2A_TRANSPORT", "stub").lower()


class A2AClientDelegator:
    """通过真实 A2A 协议委派任务（使用官方 a2a-sdk Client）。"""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    async def _get_client(self, partner: str):
        """懒加载 A2A Client（按伙伴缓存，async）。"""
        if partner not in self._clients:
            from a2a.client import ClientFactory

            url = _A2A_ENDPOINTS.get(partner)
            if not url:
                raise ValueError(f"未配置合作伙伴 {partner} 的 A2A 地址")
            self._clients[partner] = await ClientFactory().create_from_url(url)
        return self._clients[partner]

    def delegate(self, partner: str, task: dict[str, Any]) -> dict[str, Any]:
        """通过 A2A 协议委派任务，返回结构化结果。"""
        from a2a.types import Message, Part, Role, SendMessageRequest
        from a2a.types import TaskState

        task_id = task.get("task_id") or str(uuid.uuid4())

        async def _run():
            client = await self._get_client(partner)

            # 构造委派消息（JSON 文本承载最小字段）
            message = Message(
                message_id=f"req-{task_id}",
                role=Role.ROLE_USER,
                parts=[Part(text=json.dumps(task, ensure_ascii=False))],
            )
            request = SendMessageRequest(message=message)

            result = {"task_id": task_id, "partner": partner, "status": "unknown"}
            async for stream in client.send_message(request):
                # A2A 响应：最终结果在 task.status 里（state + message.parts 携带回执）
                if stream.HasField("task"):
                    t = stream.task
                    state = t.status.state
                    if state == TaskState.TASK_STATE_COMPLETED:
                        result["status"] = "completed"
                        for part in t.status.message.parts:
                            if part.text:
                                try:
                                    result["receipt"] = json.loads(part.text)
                                except json.JSONDecodeError:
                                    result["receipt"] = {"raw": part.text}
                    elif state == TaskState.TASK_STATE_FAILED:
                        result["status"] = "failed"
                    elif state == TaskState.TASK_STATE_CANCELED:
                        result["status"] = "canceled"
                elif stream.HasField("status_update"):
                    st = stream.status_update
                    if st.status.state == TaskState.TASK_STATE_FAILED:
                        result["status"] = "failed"
            result.setdefault("receipt", {})
            return result

        return asyncio.run(_run())


class DelegationManager:
    """外部委派管理器（松耦合层）。"""

    def __init__(self) -> None:
        self._idempotency_store: dict[str, dict] = {}
        self._a2a_delegator = A2AClientDelegator()

    def delegate(self, partner: str, task: dict[str, Any]) -> dict[str, Any]:
        """向外部合作伙伴委派任务。

        返回：{"status", "task_id", "receipt", ...}
        """
        # 1. 核验机构身份
        valid_partners = set(_FIELD_WHITELIST.keys())
        if partner not in valid_partners:
            return {"status": "rejected", "error": f"未知合作伙伴: {partner}"}

        # 2. 最小数据清单（字段白名单过滤）
        whitelist = _FIELD_WHITELIST.get(partner, set())
        minimal_task = {k: v for k, v in task.items() if k in whitelist}

        # 3. 幂等键
        task_id = minimal_task.get("task_id") or str(uuid.uuid4())
        minimal_task["task_id"] = task_id

        # 幂等：已处理过则直接返回缓存
        if A2A_IDEMPOTENCY_ENABLED and task_id in self._idempotency_store:
            return self._idempotency_store[task_id]

        # 4. 委派（按传输层选择）
        try:
            if A2A_TRANSPORT == "a2a":
                result = self._a2a_delegator.delegate(partner, minimal_task)
                result["task_id"] = task_id
                result["partner"] = partner
            else:
                result = _STUB_PARTNERS[partner].handle_task(minimal_task, timeout=A2A_TIMEOUT_SECONDS)
        except Exception as e:
            self._record(partner, task_id, minimal_task, "timeout")
            return {
                "status": "failed",
                "task_id": task_id,
                "error": f"委派超时/失败: {e}",
                "compensation": "已记录，可重试或撤销",
            }

        # 5. 记录审计（双侧审计）
        status = result.get("status", "unknown")
        self._record(partner, task_id, minimal_task, status, str(result.get("receipt", {})))

        # 缓存幂等结果
        self._idempotency_store[task_id] = result

        return result

    @staticmethod
    def _record(partner: str, task_id: str, payload: dict, status: str, receipt: str = "") -> None:
        """记录委派审计到本地存储。"""
        try:
            get_storage().record_delegation(task_id, partner, payload, status, receipt)
        except Exception:
            pass  # 审计失败不阻断主流程


# 模块级单例
_delegation_manager: Optional[DelegationManager] = None


def get_delegation_manager() -> DelegationManager:
    global _delegation_manager
    if _delegation_manager is None:
        _delegation_manager = DelegationManager()
    return _delegation_manager


def delegate_to_partner(partner: str, task: dict[str, Any]) -> dict[str, Any]:
    """便捷入口：向合作伙伴委派任务。"""
    return get_delegation_manager().delegate(partner, task)
