#!/usr/bin/env bash
# 等待 qwen2.5:1.5b 模型下载完成，然后切换真实 LLM 并重启服务
set -u
MODEL="qwen2.5:1.5b"
LOG="/tmp/llm_switch.log"
PROJ="/root/projects/ecom-hybrid-midplatform"

echo "[$(date)] 等待模型 $MODEL 下载完成..." >> "$LOG"

# 等待模型就绪（最多 40 分钟）
for i in $(seq 1 240); do
  if ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "[$(date)] 模型已就绪" >> "$LOG"
    break
  fi
  sleep 10
done

if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
  echo "[$(date)] 超时，模型仍未就绪" >> "$LOG"
  exit 1
fi

echo "[$(date)] 切换 LLM_PROVIDER=ollama 并重启服务..." >> "$LOG"

# 停止旧服务
pkill -f "uvicorn main:app" 2>/dev/null
sleep 2

# 以真实 LLM 模式启动
cd "$PROJ"
LLM_PROVIDER=ollama LLM_MODEL="$MODEL" nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &

sleep 5

# 验证
echo "[$(date)] 健康检查: $(curl -s http://127.0.0.1:8000/health)" >> "$LOG"

# 用真实 LLM 做一次验证
echo "[$(date)] 真实 LLM 验证:" >> "$LOG"
curl -s -X POST http://127.0.0.1:8000/chat_sync \
  -H 'Content-Type: application/json' \
  -d '{"message":"查一下商品P100的价格和库存"}' >> "$LOG" 2>&1

echo "[$(date)] 切换完成" >> "$LOG"
