"""电商混合智能中台 —— 全局配置

本地 MVP 默认使用零外部依赖的轻量存储：
- 向量库：chromadb（本地持久化，替代 Milvus）
- 关系数据：内置 SQLite（替代 PostgreSQL）
- 缓存：内置 dict / sqlite（替代 Redis）
- LLM：MockLLM 测试替身（无真实 LLM 时可完整跑通闭环）

生产环境只需替换对应 Storage 实现，业务逻辑不变。
"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "app" / "storage"

# LLM 配置：默认使用 MockLLM；设置环境变量可切换真实 LLM
# LLM_PROVIDER=mock -> MockLLM（确定性测试替身，测试/离线用）
# LLM_PROVIDER=ollama -> RealLLM（对接本机/远程 Ollama）
# LLM_PROVIDER=openai -> RealLLM（对接 OpenAI 兼容 API，如 Qwen/DashScope）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")  # ollama 默认 http://127.0.0.1:11434
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:0.5b")

# A2A 外部委派配置
A2A_TIMEOUT_SECONDS = float(os.getenv("A2A_TIMEOUT_SECONDS", "5.0"))
A2A_IDEMPOTENCY_ENABLED = os.getenv("A2A_IDEMPOTENCY_ENABLED", "1") == "1"

# 服务配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
