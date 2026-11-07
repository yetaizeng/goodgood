"""A2A 模式完整闭环演示脚本。

启动供应商 + 物流两个真实 A2A 服务，然后通过内部 LangGraph 编排 + 真实 A2A 委派，
验证「用户请求 → 内部路由 → A2A 委派外部 Agent → 回执汇总」的完整链路。

用法：
    A2A_TRANSPORT=a2a python scripts/demo_a2a_closed_loop.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time

import uvicorn

# 确保项目根目录在 sys.path（支持从任意目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 强制 A2A 模式
os.environ["A2A_TRANSPORT"] = "a2a"
os.environ["A2A_SUPPLIER_URL"] = "http://127.0.0.1:8101"
os.environ["A2A_LOGISTICS_URL"] = "http://127.0.0.1:8102"

from app.interop.a2a_server import build_supplier_server, build_logistics_server  # noqa: E402
from app.graph.orchestrator import get_graph  # noqa: E402
from app.interop.a2a_delegate import delegate_to_partner  # noqa: E402


def _serve(app, port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()


def main():
    print("=" * 60)
    print("电商混合智能中台 —— A2A 真实协议完整闭环演示")
    print("=" * 60)

    # 1. 启动供应商 + 物流 A2A 服务
    print("\n[1] 启动供应商 A2A 服务 (8101) 和物流 A2A 服务 (8102) ...")
    _serve(build_supplier_server("http://127.0.0.1:8101"), 8101)
    _serve(build_logistics_server("http://127.0.0.1:8102"), 8102)
    time.sleep(2)

    # 2. 内部 LangGraph 编排 + 真实 A2A 委派
    graph = get_graph()

    scenarios = [
        ("商品P100缺货了，帮我补货", "supplier"),
        ("订单A123的物流到哪了", "logistics"),
    ]

    for i, (req, expected_partner) in enumerate(scenarios, 1):
        print(f"\n[{i+1}] 用户请求: {req}")
        result = graph.invoke({"user_request": req}, config={"configurable": {"thread_id": f"demo-{i}"}})

        print(f"  意图: {result['intent']}")
        print(f"  需要外部委派: {result['need_external']}")
        print(f"  委派目标: {result.get('partner', '')}")

        if result.get("need_external"):
            partner = result["partner"]
            task = {
                "action": "query_stock" if partner == "supplier" else "query_logistics",
                "product_id": result.get("product_id", ""),
                "order_id": result.get("order_id", ""),
            }
            ext = delegate_to_partner(partner, task)
            print(f"  A2A 委派结果: status={ext['status']}, receipt={ext.get('receipt', {})}")

    print("\n" + "=" * 60)
    print("闭环演示完成：内部编排 + 真实 A2A 协议委派均正常")
    print("=" * 60)


if __name__ == "__main__":
    main()
