"""真实 A2A 协议端到端测试。

验证：内部系统通过真实 A2A 协议（Agent Card 发现 + Client 委派）
向供应商/物流 Agent 委派任务，收到结构化回执。

使用 FastAPI TestClient 启动 A2A 服务 + 真实 a2a-sdk Client 委派，
完整走一遍 A2A 协议栈（而非本地 stub）。
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI

from a2a.client import ClientFactory
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

from app.interop.a2a_server import build_supplier_server, build_logistics_server


def _run_server_in_thread(app: FastAPI, port: int) -> threading.Thread:
    """在独立线程启动 A2A 服务。"""
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    def _run():
        server.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


@pytest.fixture(scope="module")
def a2a_servers():
    """启动供应商(8101)和物流(8102)两个 A2A 服务。"""
    t1 = _run_server_in_thread(build_supplier_server(), 8101)
    t2 = _run_server_in_thread(build_logistics_server(), 8102)
    time.sleep(2)  # 等待服务就绪
    yield {"supplier": "http://127.0.0.1:8101", "logistics": "http://127.0.0.1:8102"}
    # teardown：daemon 线程随进程退出，无需显式关闭


def _delegate(url: str, task: dict) -> dict:
    """通过真实 A2A Client 委派任务并解析结果。"""

    async def _run():
        client = await ClientFactory().create_from_url(url)
        message = Message(
            message_id=f"req-{task.get('task_id', 'x')}",
            role=Role.ROLE_USER,
            parts=[Part(text=json.dumps(task, ensure_ascii=False))],
        )
        request = SendMessageRequest(message=message)
        result = {"status": "unknown", "receipt": None}
        async for stream in client.send_message(request):
            # A2A 响应：最终结果在 task.status 里
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
        return result

    return asyncio.run(_run())


def test_a2a_agent_card_discovery(a2a_servers):
    """验证 Agent Card 发现：ClientFactory.create_from_url 内部会拉取并解析 Agent Card。

    若 Agent Card 无法发现/解析，create_from_url 会抛异常，此测试即失败。
    """
    async def _run():
        client = await ClientFactory().create_from_url(a2a_servers["supplier"])
        return client is not None

    assert asyncio.run(_run())


def test_a2a_supplier_stock_query(a2a_servers):
    """通过真实 A2A 协议查询供应商库存。"""
    result = _delegate(a2a_servers["supplier"], {"action": "query_stock", "product_id": "P100"})
    assert result["status"] == "completed"
    assert "stock" in result["receipt"]


def test_a2a_supplier_replenish(a2a_servers):
    """通过真实 A2A 协议提交补货。"""
    result = _delegate(a2a_servers["supplier"], {"action": "replenish", "product_id": "P100", "qty": 10})
    assert result["status"] == "completed"
    assert result["receipt"]["status"] == "replenished"


def test_a2a_logistics_query(a2a_servers):
    """通过真实 A2A 协议查询物流。"""
    result = _delegate(a2a_servers["logistics"], {"action": "query_logistics", "order_id": "A123"})
    assert result["status"] == "completed"
    assert "logistics" in result["receipt"]


def test_a2a_unknown_action(a2a_servers):
    """未知 action 也返回 completed（携带 unknown_action 回执），不崩溃。"""
    result = _delegate(a2a_servers["supplier"], {"action": "do_something_weird"})
    assert result["status"] == "completed"
    assert result["receipt"]["status"] == "unknown_action"
