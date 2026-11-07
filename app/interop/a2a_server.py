"""A2A Server 工厂 —— 把供应商/物流 Agent 组装为真实 A2A 服务。

每个服务暴露：
- GET /.well-known/agent-card.json —— Agent Card（能力发现）
- POST /（JSON-RPC 消息接口）—— 接收任务委派

用法：
    supplier_app = build_supplier_server()   # 供应商 A2A 服务
    logistics_app = build_logistics_server() # 物流 A2A 服务
"""
from __future__ import annotations

from fastapi import FastAPI
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.types import AgentCard, AgentCapabilities, AgentSkill, AgentInterface

from app.interop.a2a_agents import SupplierExecutor, LogisticsExecutor


def _build_agent_card(name: str, description: str, url: str, skill_id: str, skill_name: str, skill_desc: str) -> AgentCard:
    """构造 Agent Card（能力描述），补全规范必填字段。

    url 必须是该 Agent 服务自身的真实地址（客户端据此发消息）。
    """
    return AgentCard(
        name=name,
        description=description,
        version="1.0.0",
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0.0")],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id=skill_id,
                name=skill_name,
                description=skill_desc,
                tags=["ecom", "a2a"],
                input_modes=["text"],
                output_modes=["text"],
            )
        ],
    )


def _build_server(app: FastAPI, executor, card: AgentCard) -> FastAPI:
    """把 executor + card 组装为带 A2A 路由的 FastAPI 应用。"""
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    agent_card_routes = create_agent_card_routes(card)
    jsonrpc_routes = create_jsonrpc_routes(handler, rpc_url="/")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=agent_card_routes,
        jsonrpc_routes=jsonrpc_routes,
    )
    return app


def build_supplier_server(url: str = "http://127.0.0.1:8101") -> FastAPI:
    """供应商 Agent 的 A2A 服务。"""
    card = _build_agent_card(
        name="Ecom Supplier Agent",
        description="电商供应商 Agent：库存查询与补货委派",
        url=url,
        skill_id="supplier_inventory",
        skill_name="库存与补货",
        skill_desc="查询库存、提交补货申请",
    )
    app = FastAPI(title="Ecom Supplier A2A Server")
    return _build_server(app, SupplierExecutor(), card)


def build_logistics_server(url: str = "http://127.0.0.1:8102") -> FastAPI:
    """物流 Agent 的 A2A 服务。"""
    card = _build_agent_card(
        name="Ecom Logistics Agent",
        description="电商物流 Agent：配送与物流查询委派",
        url=url,
        skill_id="logistics_delivery",
        skill_name="物流配送",
        skill_desc="查询物流、委派配送",
    )
    app = FastAPI(title="Ecom Logistics A2A Server")
    return _build_server(app, LogisticsExecutor(), card)
