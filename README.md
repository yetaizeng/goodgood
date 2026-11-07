# 电商混合智能中台（Ecom Hybrid Midplatform）

> 内部紧耦合 + 外部松耦合的分层设计 —— LangGraph 编排 + A2A 外部委派 + MCP 工具标准化
>
> A hybrid-architecture e-commerce agent system: internal LangGraph orchestration + external A2A delegation + MCP tool standardization.

## 一、项目简介

电商场景下的混合架构 Agent 系统：

- **内部（紧耦合）**：LangGraph 状态图编排 4 个业务 Agent（商品/订单/客服/营销），共享 state 和 checkpoint，Orchestrator 统一路由。
- **外部（松耦合）**：A2A 协议向供应商/物流 Agent 委派任务（库存查询、补货、物流跟踪），回执验签 + 幂等 + 超时补偿。
- **工具层（标准化）**：MCP（FastMCP）封装读写分级工具，只读工具无门槛，写工具需内部授权。

### 核心亮点（面试可讲）

| 维度 | 设计 |
|------|------|
| 分层 | 内部紧耦合（共享 state/checkpoint）+ 外部松耦合（独立信任边界） |
| 护栏 | 外部 Agent 默认无内部读写权限；写操作需人工确认 |
| 状态分离 | 内部 Checkpoint 与外部任务 ID 分离，互不污染 |
| 最小数据 | 跨机构只交换任务所需最小字段（字段白名单） |
| 工具分级 | MCP 工具按读写权限分级（只读 vs 需审批） |
| 幂等与补偿 | 委派幂等键 + 回执验签 + 超时补偿 |

## 二、目录结构

```
ecom-hybrid-midplatform/
├── main.py                  # FastAPI 入口（SSE + MCP 挂载）
├── requirements.txt
├── app/
│   ├── config.py            # 全局配置
│   ├── graph/
│   │   ├── state.py         # 内部共享 state（含 checkpoint）
│   │   ├── orchestrator.py  # LangGraph 编排 + 条件路由
│   │   └── agents/          # 商品/订单/客服/营销 4 个 Agent
│   ├── interop/
│   │   ├── partner_stubs.py # 供应商/物流 Agent 测试替身
│   │   └── a2a_delegate.py  # A2A 委派管理器（验签/幂等/补偿）
│   ├── tools/
│   │   ├── mcp_tools.py     # 读写分级工具实现
│   │   └── mcp_server.py    # FastMCP Server 定义
│   ├── storage/
│   │   └── store.py         # SQLite 存储（含护栏校验）
│   └── llm/
│       └── mock.py          # MockLLM 测试替身
├── tests/
│   └── test_hybrid_flow.py  # 14 个闭环测试
├── scripts/
│   ├── deploy.sh            # Linux 一键部署脚本
│   └── remote_deploy.py     # paramiko 远程部署脚本
└── data/                    # 种子数据
```

## 三、本地运行（Windows / 开发环境）

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate        # Linux
# .venv\Scripts\activate          # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行测试
python -m pytest tests/ -v

# 4. 启动服务
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## 四、接口说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/chat_sync` | POST | 同步接口（便于调试），body: `{"message": "..."}` |
| `/chat` | POST | SSE 流式接口，body: `{"message": "..."}` |
| `/mcp` | POST | MCP 端点（FastMCP http_app） |

### 示例

```bash
# 内部编排
curl -X POST http://127.0.0.1:8000/chat_sync \
  -H 'Content-Type: application/json' \
  -d '{"message":"查一下商品P100的价格和库存"}'

# 外部委派（补货 -> 供应商）
curl -X POST http://127.0.0.1:8000/chat_sync \
  -H 'Content-Type: application/json' \
  -d '{"message":"商品P100缺货了，帮我补货"}'

# 外部委派（物流 -> 物流商）
curl -X POST http://127.0.0.1:8000/chat_sync \
  -H 'Content-Type: application/json' \
  -d '{"message":"订单A123的物流到哪了"}'
```

## 五、测试覆盖（14 个用例）

1. **意图路由**（4 个）：product / order / service / marketing 正确路由
2. **共享 state 与汇总**：内部编排产出最终摘要
3. **外部委派路由**：物流→logistics、补货→supplier 正确匹配
4. **A2A 委派**（5 个）：库存查询、补货、物流查询、幂等、未知伙伴拒绝
5. **护栏**（3 个）：外部 Agent 无写权限、内部授权可写、补货需授权

## 六、设计原则（来自项目文档 P19 跨机构受控协作）

- **证据链**：核验机构身份、合同与用途授权 → 字段白名单 → 最小材料
- **决策**：区分内部可信状态与外部回执 → 校验签名/幂等/超时/版本 → 高风险转人工
- **交付**：内部负责人确认后委派 → 接收回执/核对/补偿 → 留存双侧审计
- **护栏**：外部 Agent 不自动取得内部读写权限

## 七、生产替换路径

| 组件 | 本地 MVP | 生产 |
|------|----------|------|
| 向量库 | chromadb（或 SQLite） | Milvus |
| 关系库 | SQLite | PostgreSQL |
| 缓存 | 内存 dict | Redis |
| LLM | MockLLM | Qwen / OpenAI API |
| 外部伙伴 | 本地替身 stub | 远端 A2A Agent（Agent Card 发现） |

业务逻辑与接口契约不变，仅替换 Storage / LLM / 伙伴端点实现。

## 八、LLM 切换（MockLLM ↔ RealLLM）

项目内置两套 LLM 实现，通过环境变量 `LLM_PROVIDER` 一键切换：

| LLM_PROVIDER | 实现 | 用途 |
|--------------|------|------|
| `mock`（默认） | MockLLM | 测试/离线，确定性可断言 |
| `ollama` | RealLLM | 本地 Ollama，免费离线，演示推荐 |
| `openai` | RealLLM | OpenAI 兼容 API（Qwen/DashScope 等） |

```bash
# 测试：保持默认（mock），保证确定性
python -m pytest tests/ -v

# 演示：切到 Ollama（需先启动 Ollama 并拉模型）
ollama pull qwen2.5:0.5b
LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:0.5b python -m uvicorn main:app --port 8000

# 或对接远程 OpenAI 兼容 API
export LLM_PROVIDER=openai
export LLM_MODEL=qwen-plus
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LLM_API_KEY=sk-xxx
```

**设计原则**：真实 LLM 有随机性，因此**只在运行时使用**；单元测试永远用 MockLLM 保证确定性。两者实现同一接口（`classify_intent` / `generate_summary` / `generate_draft`），业务代码零改动。

## 九、虚拟机 Ollama 部署（自包含真实 LLM）

虚拟机（192.168.88.101）可用 Docker 跑 Ollama，实现项目自包含：

```bash
# 方式一：手动（镜像拉取完成后）
bash scripts/setup_ollama.sh qwen2.5:1.5b

# 方式二：后台自动（等待镜像 → 启动容器 → 拉模型，日志在 /tmp/ollama_setup.log）
nohup bash scripts/ollama_wait_and_setup.sh qwen2.5:1.5b > /tmp/ollama_setup.log 2>&1 &
```

Ollama 就绪后，虚拟机服务切换真实 LLM：

```bash
# 虚拟机内
cd /root/projects/ecom-hybrid-midplatform
export LLM_PROVIDER=ollama
export LLM_MODEL=qwen2.5:1.5b
export LLM_BASE_URL=http://127.0.0.1:11434
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

> 注意：VMware NAT 下虚拟机无法反向访问宿主机（192.168.88.1），故采用虚拟机自建 Ollama 而非共享宿主机模型。

## 十、A2A 真实协议化（外部委派双模式）

外部委派支持两种传输层，通过环境变量 `A2A_TRANSPORT` 切换：

| A2A_TRANSPORT | 实现 | 说明 |
|---------------|------|------|
| `stub`（默认） | 本地替身 | 确定性，测试用，无需起服务 |
| `a2a` | 真实 A2A 协议 | Agent Card 发现 + JSON-RPC 委派，面试演示用 |

### 真实 A2A 协议实现

- **服务端**（`app/interop/a2a_agents.py` + `a2a_server.py`）：供应商/物流 Agent 通过官方 `a2a-sdk` 实现 `AgentExecutor`，暴露 `/.well-known/agent-card.json`（Agent Card 能力发现）+ JSON-RPC 消息接口。
- **客户端**（`app/interop/a2a_delegate.py` 的 `A2AClientDelegator`）：通过 `ClientFactory` 发现 Agent Card 并委派任务，解析 `task.status` 回执。
- **任务状态流转**：submitted → working → completed（回执以 JSON 文本携带在 `task.status.message.parts`）。

### 演示完整闭环

```bash
# 内部编排 + 真实 A2A 委派（供应商/物流）
python scripts/demo_a2a_closed_loop.py
```

### 测试

```bash
# 真实 A2A 协议端到端测试（起两个 A2A 服务 + Client 委派）
python -m pytest tests/test_a2a_protocol.py -v
```

> 核心护栏不变：外部 Agent 输出视为不可信输入，不自动取得内部读写权限；字段白名单 + 幂等键 + 双侧审计在真实 A2A 模式下同样生效。
