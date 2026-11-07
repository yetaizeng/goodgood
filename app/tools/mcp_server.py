"""MCP Server 定义 —— 用 FastMCP 暴露标准工具端点。

读写分级：只读工具无门槛；写工具需通过 operator 校验。
"""
from __future__ import annotations

from fastmcp import FastMCP

from app import tools as tool_impl

# 创建 MCP Server 实例
mcp = FastMCP("ecom-midplatform")


@mcp.tool()
def query_product(product_id: str) -> dict:
    """查询商品信息（只读）"""
    return tool_impl.query_product(product_id)


@mcp.tool()
def list_products(category: str = None) -> list:
    """列出商品（只读）"""
    return tool_impl.list_products(category)


@mcp.tool()
def query_order(order_id: str) -> dict:
    """查询订单信息（只读）"""
    return tool_impl.query_order(order_id)


@mcp.tool()
def get_reviews(product_id: str) -> list:
    """查询商品评价（只读）"""
    return tool_impl.get_reviews(product_id)


@mcp.tool()
def submit_replenish(product_id: str, qty: int, operator: str = "internal-operator") -> dict:
    """提交补货申请（受控写，需内部授权）"""
    return tool_impl.submit_replenish(product_id, qty, operator)


@mcp.tool()
def update_order_status(order_id: str, status: str, operator: str = "internal-operator") -> dict:
    """更新订单状态（受控写，需内部授权）"""
    return tool_impl.update_order_status(order_id, status, operator)


def get_mcp_server() -> FastMCP:
    return mcp
