"""llm 包：LLM 接入层（MockLLM 测试替身 + RealLLM 真实调用）。"""
from app.llm.mock import MockLLM, get_llm
from app.llm.real import RealLLM

__all__ = ["MockLLM", "RealLLM", "get_llm"]
