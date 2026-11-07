#!/usr/bin/env bash
# 虚拟机 Ollama 一键部署 + 拉模型脚本
# 用法：bash /root/projects/ecom-hybrid-midplatform/scripts/setup_ollama.sh
set -euo pipefail

MODEL="${1:-qwen2.5:1.5b}"

echo "=== 1. 启动 Ollama 容器 ==="
if docker ps --format '{{.Names}}' | grep -q '^ollama$'; then
  echo "Ollama 容器已在运行"
else
  docker rm -f ollama 2>/dev/null || true
  docker run -d --name ollama \
    -p 11434:11434 \
    -v ollama:/root/.ollama \
    --restart unless-stopped \
    ollama/ollama:latest
  echo "Ollama 容器已启动"
fi

# 等待服务就绪
sleep 3

echo "=== 2. 拉取模型 $MODEL ==="
docker exec ollama ollama pull "$MODEL"

echo "=== 3. 验证 ==="
docker exec ollama ollama list

echo ""
echo "Ollama 已就绪：http://192.168.88.101:11434"
echo "模型：$MODEL"
