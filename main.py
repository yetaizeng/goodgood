"""电商混合智能中台 —— FastAPI 入口。

流程：
用户请求 → 内部 Orchestrator 路由 → LangGraph Agent 协作(共享 state)
        → 需外部数据时 A2A 委派供应商/物流 Agent → MCP 调用标准工具
        → 结果汇总 SSE 返回

启动：python main.py  （或 uvicorn main:app）
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.graph.orchestrator import get_graph
from app.interop.a2a_delegate import delegate_to_partner
from app.tools.mcp_server import get_mcp_server

app = FastAPI(title="电商混合智能中台", version="1.0.0")

# MCP 端点：以 ASGI app 方式挂载到 /mcp 路径
mcp = get_mcp_server()
app.mount("/mcp", mcp.http_app())

# 静态前端演示页面
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


def _extract_product_id(text: str) -> str:
    import re

    m = re.search(r"P\d+", text)
    return m.group(0) if m else ""


def _extract_order_id(text: str) -> str:
    import re

    m = re.search(r"A\d+", text)
    return m.group(0) if m else ""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ecom-hybrid-midplatform"}


@app.get("/")
async def index() -> FileResponse:
    """前端演示页面入口。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """SSE 流式返回：内部编排 + 外部委派 + 汇总。"""
    thread_id = req.thread_id or str(uuid.uuid4())

    async def event_stream() -> AsyncGenerator[str, None]:
        graph = get_graph()

        # 1. 内部 LangGraph 编排（共享 state + checkpoint）
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = graph.invoke({"user_request": req.message}, config=config)
        except Exception as e:
            yield _sse({"type": "error", "message": f"内部编排失败: {e}"})
            return

        yield _sse({"type": "intent", "intent": result.get("intent"), "thread_id": thread_id})
        yield _sse({"type": "checkpoint", "checkpoint": result.get("checkpoint", {})})

        # 2. 外部 A2A 委派（如需要）
        if result.get("need_external"):
            partner = result.get("partner", "supplier")
            task = {
                "action": "query_stock" if partner == "supplier" else "query_logistics",
                "product_id": result.get("product_id", ""),
                "order_id": result.get("order_id", ""),
            }
            ext = delegate_to_partner(partner, task)
            yield _sse({"type": "a2a_delegation", "partner": partner, "result": ext})

        # 3. 结果汇总
        yield _sse({"type": "final", "summary": result.get("final_summary", "")})
        yield _sse({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat_sync")
async def chat_sync(req: ChatRequest) -> dict[str, Any]:
    """同步接口（便于测试/调试）。"""
    graph = get_graph()
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"user_request": req.message}, config=config)

    ext = None
    if result.get("need_external"):
        partner = result.get("partner", "supplier")
        task = {
            "action": "query_stock" if partner == "supplier" else "query_logistics",
            "product_id": result.get("product_id", ""),
            "order_id": result.get("order_id", ""),
        }
        ext = delegate_to_partner(partner, task)

    return {
        "intent": result.get("intent"),
        "checkpoint": result.get("checkpoint", {}),
        "final_summary": result.get("final_summary", ""),
        "external": ext,
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
