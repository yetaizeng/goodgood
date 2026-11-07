"""通过 paramiko 连接虚拟机，探测环境。"""
import paramiko

HOST = "192.168.88.101"
USER = "root"
PWD = "123456"


def run(cmd: str, timeout: int = 30) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PWD, timeout=10)
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    client.close()
    return (out + err).strip()


if __name__ == "__main__":
    print("=== OS 信息 ===")
    print(run("uname -a; cat /etc/os-release 2>/dev/null | head -3"))
    print("\n=== Python 版本 ===")
    print(run("python3 --version 2>&1; python --version 2>&1; pip3 --version 2>&1"))
    print("\n=== 已装关键依赖 ===")
    print(run("python3 -c \"import langgraph, fastapi, fastmcp; print('langgraph/fastapi/fastmcp OK')\" 2>&1 || python -c \"import langgraph, fastapi, fastmcp; print('langgraph/fastapi/fastmcp OK')\" 2>&1"))
    print("\n=== Docker ===")
    print(run("docker --version 2>&1; docker ps 2>&1 | head -3"))
    print("\n=== 磁盘/内存 ===")
    print(run("df -h / 2>/dev/null | tail -1; free -h 2>/dev/null | head -2"))
