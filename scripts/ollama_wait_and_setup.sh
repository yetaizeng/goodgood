#!/usr/bin/env bash
# 后台任务：等待 ollama 镜像下载完成，然后启动容器并拉模型
# 用法：nohup bash /root/projects/ecom-hybrid-midplatform/scripts/ollama_wait_and_setup.sh > /tmp/ollama_setup.log 2>&1 &
set -u

MODEL="${1:-qwen2.5:1.5b}"
LOG="/tmp/ollama_setup.log"

echo "[$(date)] 开始等待 ollama 镜像..." >> "$LOG"

# 等待镜像下载完成（最多等 30 分钟）
for i in $(seq 1 180); do
  if docker images -q ollama/ollama 2>/dev/null | grep -q .; then
    echo "[$(date)] 镜像已就绪" >> "$LOG"
    break
  fi
  # 若 pull 进程都没了且镜像还没好，说明下载失败，重试一次
  if ! pgrep -f "docker pull ollama" >/dev/null; then
    echo "[$(date)] pull 进程中断，重试..." >> "$LOG"
    nohup docker pull ollama/ollama:latest >> /tmp/ollama_pull.log 2>&1 &
  fi
  sleep 10
done

if ! docker images -q ollama/ollama 2>/dev/null | grep -q .; then
  echo "[$(date)] 超时，镜像仍不可用" >> "$LOG"
  exit 1
fi

# 启动容器
echo "[$(date)] 启动 ollama 容器" >> "$LOG"
docker rm -f ollama 2>/dev/null
docker run -d --name ollama \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  --restart unless-stopped \
  ollama/ollama:latest >> "$LOG" 2>&1

sleep 5

# 拉模型
echo "[$(date)] 拉取模型 $MODEL" >> "$LOG"
docker exec ollama ollama pull "$MODEL" >> "$LOG" 2>&1

echo "[$(date)] 完成。模型列表：" >> "$LOG"
docker exec ollama ollama list >> "$LOG" 2>&1

echo "[$(date)] Ollama 就绪: http://192.168.88.101:11434, 模型=$MODEL" >> "$LOG"
