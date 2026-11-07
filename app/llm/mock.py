"""MockLLM —— 语义明确的 LLM 测试替身

设计原则（与项目约定一致）：
- 缺少真实 LLM 时，用「确定性规则」模拟 LLM 的两个核心职责：
  1. 意图分类（intent classification）
  2. 结构化生成（structured generation）
- 绝不伪造“看起来像真的”随机输出；每个输出都可由输入确定性地推导，
  便于测试断言与验收。
"""
from __future__ import annotations

from typing import Any


class MockLLM:
    """确定性的 LLM 替身，用于离线闭环与测试。"""

    def __init__(self) -> None:
        self._call_count = 0

    # ------------------------------------------------------------------
    # 意图分类：根据用户请求关键词，映射到 4 个内部业务 Agent
    # ------------------------------------------------------------------
    # 注意：规则顺序即优先级。强信号（投诉/退款/售后）须排在弱信号（商品/价格）之前，
    # 否则「投诉商品质量问题」会误判为 product。
    INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
        ("service", ("投诉", "维权", "质量问题", "退货政策", "保修", "客服")),
        ("order", ("订单", "物流", "快递", "发货", "退款", "换货", "售后", "配送", "到哪")),
        ("marketing", ("营销", "促销", "优惠券", "文案", "推广", "折扣")),
        ("product", ("价格", "库存", "规格", "参数", "多少钱", "有货", "商品")),
    ]

    def classify_intent(self, user_request: str) -> str:
        """确定性意图分类：按关键词命中优先级返回意图。

        无命中时回退到 'service'（客服），并保留原始文本供后续处理。
        """
        for intent, keywords in self.INTENT_RULES:
            if any(kw in user_request for kw in keywords):
                return intent
        return "service"

    # ------------------------------------------------------------------
    # 结构化生成：从事实字段生成可解释的回复草稿（不补写不存在的事实）
    # ------------------------------------------------------------------
    def generate_summary(self, intent: str, facts: dict[str, Any]) -> str:
        """基于事实字段生成确定性摘要。

        - 只使用传入的 facts，不虚构字段。
        - 输出格式固定，便于断言。
        """
        self._call_count += 1
        lines = [f"[MockLLM] 意图={intent}"]
        for key, value in facts.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)

    def generate_draft(self, template: str, fields: dict[str, Any]) -> str:
        """按模板 + 字段生成草稿（事实约束生成）。"""
        self._call_count += 1
        try:
            return template.format(**fields)
        except (KeyError, IndexError):
            # 缺失字段时明确标注，不静默补写
            missing = [k for k in fields if "{" + k + "}" in template and k not in fields]
            return template + f" [缺失字段: {', '.join(missing) if missing else '无'}]"

    @property
    def call_count(self) -> int:
        return self._call_count


def get_llm():
    """工厂：根据 LLM_PROVIDER 环境变量切换实现。

    - LLM_PROVIDER=ollama / openai -> 返回 RealLLM（真实调用）
    - 其他 / 未设置 -> 返回 MockLLM（确定性测试替身）

    注意：Agent 节点与 Orchestrator 通过 get_llm() 获取实例，
    因此切换只需改环境变量，业务代码零改动。
    """
    import os

    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider in ("ollama", "openai"):
        from app.llm.real import get_real_llm

        return get_real_llm()
    return MockLLM()
