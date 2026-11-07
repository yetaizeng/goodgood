"""A2A Agent 执行器 —— 供应商 / 物流 Agent 的真实 A2A 服务端实现。

用官方 a2a-sdk 实现 AgentExecutor 接口：
- execute(context, event_queue)：接收外部委派任务，处理并回传结果
- 任务状态流转：submitted -> working -> completed

这是「外部松耦合」层的真实实现：外部 Agent 通过 A2A 协议暴露能力，
内部系统通过 A2A Client 委派任务（不再用本地 stub）。
"""
from __future__ import annotations

import json
import time
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)


def _initial_task(task_id: str, context_id: str) -> Task:
    """构造初始 Task（协议要求先 enqueue Task 再发状态更新）。"""
    return Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
    )


def _make_task_status(task_id: str, state, message: str | None = None) -> TaskStatusUpdateEvent:
    """构造任务状态更新事件。"""
    msg = None
    if message:
        msg = Message(
            message_id=f"msg-{task_id}",
            role=Role.ROLE_AGENT,
            parts=[Part(text=message)],
        )
    status = TaskStatus(state=state, message=msg)
    return TaskStatusUpdateEvent(task_id=task_id, status=status)


def _working(task_id: str) -> TaskStatusUpdateEvent:
    return _make_task_status(task_id, TaskState.TASK_STATE_WORKING)


def _completed(task_id: str, result: dict[str, Any]) -> TaskStatusUpdateEvent:
    """完成并携带结构化结果（JSON 文本）。"""
    return _make_task_status(
        task_id,
        TaskState.TASK_STATE_COMPLETED,
        message=json.dumps(result, ensure_ascii=False),
    )


class SupplierExecutor(AgentExecutor):
    """供应商 Agent：处理库存查询 / 补货委派（真实 A2A 服务端）。"""

    def __init__(self) -> None:
        self._stock = {"P100": 50, "P101": 30, "P102": 200}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id
        # 解析委派消息（文本格式：action:product_id:qty）
        action, product_id, qty = self._parse(context)

        # 0. 先 enqueue 初始 Task（协议要求：Task 必须在状态更新之前）
        await event_queue.enqueue_event(_initial_task(task_id, context.context_id))

        # 1. 标记 working
        await event_queue.enqueue_event(_working(task_id))

        # 2. 处理业务
        if action == "query_stock":
            result = {"stock": self._stock.get(product_id, 0), "checked_at": time.time()}
        elif action == "replenish":
            added = qty or 0
            self._stock[product_id] = self._stock.get(product_id, 0) + added
            result = {"status": "replenished", "eta": "3d", "added": added}
        else:
            result = {"status": "unknown_action", "action": action}

        # 3. 完成并回传结果
        await event_queue.enqueue_event(_completed(task_id, result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            _make_task_status(context.task_id, TaskState.TASK_STATE_CANCELED, "已取消")
        )

    @staticmethod
    def _parse(context: RequestContext) -> tuple[str, str, int]:
        """从委派消息中解析 action/product_id/qty。"""
        action, product_id, qty = "query_stock", "", 0
        try:
            msg = context.message
            for part in msg.parts:
                if part.text:
                    # 支持 JSON 或 简单文本格式
                    try:
                        data = json.loads(part.text)
                        action = data.get("action", action)
                        product_id = data.get("product_id", "")
                        qty = int(data.get("qty", 0))
                    except json.JSONDecodeError:
                        # 简单格式：action:product_id:qty
                        segs = part.text.split(":")
                        action = segs[0] if len(segs) > 0 else action
                        product_id = segs[1] if len(segs) > 1 else ""
                        qty = int(segs[2]) if len(segs) > 2 and segs[2].isdigit() else 0
        except Exception:
            pass
        return action, product_id, qty


class LogisticsExecutor(AgentExecutor):
    """物流 Agent：处理配送 / 物流查询委派（真实 A2A 服务端）。"""

    def __init__(self) -> None:
        self._shipments: dict[str, str] = {
            "A123": "SF1234567890 在途，预计2日内送达",
            "A124": "待发货，预计明日发出",
        }

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id
        action, order_id = self._parse(context)

        # 0. 先 enqueue 初始 Task（协议要求）
        await event_queue.enqueue_event(_initial_task(task_id, context.context_id))

        await event_queue.enqueue_event(_working(task_id))

        if action == "query_logistics":
            result = {"logistics": self._shipments.get(order_id, "无该订单物流信息"), "checked_at": time.time()}
        elif action == "dispatch":
            result = {"status": "dispatched", "courier": "SF", "eta": "1d"}
        else:
            result = {"status": "unknown_action", "action": action}

        await event_queue.enqueue_event(_completed(task_id, result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            _make_task_status(context.task_id, TaskState.TASK_STATE_CANCELED, "已取消")
        )

    @staticmethod
    def _parse(context: RequestContext) -> tuple[str, str]:
        action, order_id = "query_logistics", ""
        try:
            for part in context.message.parts:
                if part.text:
                    try:
                        data = json.loads(part.text)
                        action = data.get("action", action)
                        order_id = data.get("order_id", "")
                    except json.JSONDecodeError:
                        segs = part.text.split(":")
                        action = segs[0] if segs else action
                        order_id = segs[1] if len(segs) > 1 else ""
        except Exception:
            pass
        return action, order_id
