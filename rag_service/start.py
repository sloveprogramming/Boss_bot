"""RAG Service 启动脚本

用法:
    python start.py
"""
import subprocess
import sys
import os


def main():
    # 确保工作目录正确
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 使用父目录的 .env（共享 LLM/Milvus 配置）
    parent_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(parent_env):
        os.environ["ENV_FILE"] = parent_env

    print("=" * 50)
    print("  启动 RAG Service")
    print("  API:   http://localhost:18003")
    print("  文档:  http://localhost:18003/docs")
    print("=" * 50)

    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--app-dir", "src",
        "--host", "0.0.0.0",
        "--port", "18003",
        "--reload",
    ]
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
