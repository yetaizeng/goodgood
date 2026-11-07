#!/usr/bin/env bash
# 电商混合智能中台 —— Linux 虚拟机一键部署脚本
# 用法：在项目根目录执行  bash scripts/deploy.sh
# 前提：root 用户，CentOS Stream 9（含 python3.11）
set -euo pipefail

echo "=============================================="
echo " 电商混合智能中台 —— 一键部署"
echo "=============================================="

# 1. 检测 Python 3.11
PY=""
for cand in python3.11 python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "[错误] 未找到 python3.11+，请先安装"
  exit 1
fi
echo "[1/5] 使用 Python: $PY ($($PY --version 2>&1))"

# 2. 创建虚拟环境
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "[2/5] 创建虚拟环境 $VENV_DIR ..."
  $PY -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
python -m pip install --quiet --upgrade pip

# 3. 安装依赖
echo "[3/5] 安装依赖（可能需要几分钟）..."
pip install --quiet -r requirements.txt

# 4. 运行测试
echo "[4/5] 运行测试 ..."
python -m pytest tests/ -v

# 5. 启动服务
echo "[5/5] 启动服务（后台，端口 8000）..."
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo "服务已启动，PID=$!"
sleep 2
curl -s http://127.0.0.1:8000/health && echo "" || echo "[警告] 健康检查未通过，查看 server.log"

echo "=============================================="
echo " 部署完成！"
echo "  健康检查: http://192.168.88.101:8000/health"
echo "  同步接口: POST http://192.168.88.101:8000/chat_sync"
echo "  流式接口: POST http://192.168.88.101:8000/chat"
echo "  MCP 端点: http://192.168.88.101:8000/mcp"
echo "=============================================="
