"""RealLLM —— 真实 LLM 接入（Ollama / OpenAI 兼容）。

与 MockLLM 实现同一套接口（classify_intent / generate_summary / generate_draft），
通过环境变量 LLM_PROVIDER 切换：
- LLM_PROVIDER=ollama  -> 走本机/远程 Ollama 的 /api/chat
- LLM_PROVIDER=openai  -> 走 OpenAI 兼容 API（Qwen/DashScope 等）
- 其他/未设置        -> 回退 MockLLM

设计原则：真实 LLM 有随机性，因此仅在运行时使用；测试仍用 MockLLM 保证确定性。
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx


class RealLLM:
    """对接真实 LLM 的运行时实现（Ollama 或 OpenAI 兼容）。"""

    def __init__(
        self,
        provider: str = "ollama",
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.provider = provider
        self.model = model or os.getenv("LLM_MODEL", "qwen2.5:7b")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.timeout = timeout

        if provider == "ollama":
            # 默认连本机 Ollama；可用 LLM_BASE_URL 覆盖（如指向虚拟机 Ollama）
            self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        else:  # openai 兼容
            self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")

    # ------------------------------------------------------------------
    # 意图分类
    # ------------------------------------------------------------------
    def classify_intent(self, user_request: str) -> str:
        """用真实 LLM 做意图分类，返回 product/order/service/marketing 之一。"""
        prompt = (
            "你是电商智能中台的意图分类器。请将用户请求分类为以下四类之一，"
            "只输出类别名，不要输出其他内容：\n"
            "- product：查询商品、价格、库存、规格\n"
            "- order：查询订单、物流、退款、售后进度\n"
            "- service：投诉、咨询、售后政策、帮助\n"
            "- marketing：营销、促销、文案、优惠\n\n"
            f"用户请求：{user_request}\n"
            "类别："
        )
        raw = self._complete(prompt, max_tokens=16).strip().lower()
        # 归一化：从模型输出中提取合法意图
        for intent in ("product", "order", "service", "marketing"):
            if intent in raw:
                return intent
        # 兜底：无法识别时回退 service，并保留原始文本
        return "service"

    # ------------------------------------------------------------------
    # 结构化生成
    # ------------------------------------------------------------------
    def generate_summary(self, intent: str, facts: dict[str, Any]) -> str:
        """基于事实字段生成可解释的摘要（事实约束，不补写）。"""
        facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items())
        prompt = (
            f"你是电商客服助手。根据以下【意图】和【事实】生成一段简洁、"
            f"只基于事实、不虚构信息的答复：\n\n"
            f"【意图】{intent}\n"
            f"【事实】\n{facts_str}\n\n"
            f"请直接输出答复正文："
        )
        return self._complete(prompt, max_tokens=256).strip()

    def generate_draft(self, template: str, fields: dict[str, Any]) -> str:
        """按模板 + 字段生成营销文案草稿（事实约束生成）。"""
        fields_str = "\n".join(f"- {k}: {v}" for k, v in fields.items())
        prompt = (
            f"你是电商营销文案助手。根据以下商品事实生成一条简短有吸引力的营销文案，"
            f"只使用给定事实，不虚构价格、规格：\n\n"
            f"【商品事实】\n{fields_str}\n\n"
            f"请直接输出营销文案："
        )
        return self._complete(prompt, max_tokens=256).strip()

    # ------------------------------------------------------------------
    # 底层补全
    # ------------------------------------------------------------------
    def _complete(self, prompt: str, max_tokens: int = 256) -> str:
        """统一底层调用：Ollama /chat 或 OpenAI /chat/completions。"""
        if self.provider == "ollama":
            return self._complete_ollama(prompt, max_tokens)
        return self._complete_openai(prompt, max_tokens)

    def _complete_ollama(self, prompt: str, max_tokens: int) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.2},
        }
        # trust_env=False 禁用系统代理，避免 localhost 请求被代理转发导致超时
        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}).get("content", "")

    def _complete_openai(self, prompt: str, max_tokens: int) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        # trust_env=False 禁用系统代理（Ollama 走 localhost，不应经过代理）
        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


def get_real_llm() -> RealLLM:
    """根据环境变量构造 RealLLM。"""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    return RealLLM(provider=provider)
