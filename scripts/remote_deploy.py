"""远程部署脚本：通过 paramiko 将项目上传到虚拟机并完成部署 + 运行。

流程：
1. 打包本地项目源码（排除 venv/缓存）
2. 上传到虚拟机 /root/projects/ecom-hybrid-midplatform
3. 用 python3.11 创建 venv 并安装依赖
4. 运行 pytest 测试
5. 启动 uvicorn 服务并健康检查
"""
import io
import os
import tarfile
import time

import paramiko

HOST = "192.168.88.101"
USER = "root"
PWD = "123456"
PORT = 22

REMOTE_DIR = "/root/projects/ecom-hybrid-midplatform"
LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDE = {".venv", "__pycache__", ".pytest_cache", "*.pyc", "*.sqlite", "node_modules", ".git"}


def build_tar() -> bytes:
    """将本地项目打包为 tar 字节流。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(LOCAL_DIR):
            # 排除目录
            dirs[:] = [
                d
                for d in dirs
                if d not in EXCLUDE and d not in {".venv", "__pycache__", ".pytest_cache", ".git"}
            ]
            for f in files:
                if f.endswith((".pyc", ".sqlite")):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, LOCAL_DIR)
                tar.add(full, arcname=rel)
    return buf.getvalue()


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {HOST}:{PORT} ...")
    client.connect(HOST, port=PORT, username=USER, password=PWD, timeout=15)

    def run(cmd: str, timeout: int = 300) -> str:
        _, o, e = client.exec_command(cmd, timeout=timeout)
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        return (out + err).strip()

    # 1. 创建远程目录
    print("创建远程目录 ...")
    run(f"mkdir -p {REMOTE_DIR}")

    # 2. 上传项目
    print("打包并上传项目 ...")
    data = build_tar()
    print(f"  项目包大小: {len(data)/1024:.1f} KB")
    sftp = client.open_sftp()
    with sftp.open(f"{REMOTE_DIR}/deploy.tar.gz", "wb") as f:
        f.write(data)
    sftp.close()
    run(f"cd {REMOTE_DIR} && tar xzf deploy.tar.gz && rm deploy.tar.gz")
    print("  上传解压完成")

    # 3. 检查 python3.11 并准备 pip
    print("准备 Python 3.11 环境 ...")
    run("python3.11 -m ensurepip --upgrade 2>&1 | tail -2 || true")

    # 4. 创建 venv（若不存在）
    print("创建/复用虚拟环境 ...")
    run(f"cd {REMOTE_DIR} && [ -d .venv ] || python3.11 -m venv .venv")

    # 5. 安装依赖（可能耗时）
    print("安装依赖（可能需要几分钟）...")
    print(run(
        f"cd {REMOTE_DIR} && .venv/bin/pip install --quiet --upgrade pip && "
        f".venv/bin/pip install --quiet -r requirements.txt 2>&1 | tail -15"
    ))

    # 6. 运行测试
    print("运行测试 ...")
    test_out = run(f"cd {REMOTE_DIR} && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -30")
    print(test_out)

    # 7. 停止旧服务（如有）
    run("pkill -f 'uvicorn main:app' 2>/dev/null || true")

    # 8. 启动服务
    print("启动服务 ...")
    run(f"cd {REMOTE_DIR} && nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 & echo started")
    time.sleep(3)

    # 9. 健康检查
    print("健康检查 ...")
    health = run("curl -s http://127.0.0.1:8000/health")
    print(f"  结果: {health}")

    client.close()
    print("\n=== 部署完成 ===")
    print(f"  健康检查: http://{HOST}:8000/health")
    print(f"  同步接口: POST http://{HOST}:8000/chat_sync")
    print(f"  流式接口: POST http://{HOST}:8000/chat")


if __name__ == "__main__":
    main()
