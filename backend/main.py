"""
一键启动入口（开发 / 演示）

在 backend/ 目录下执行：

    python main.py

即可启动服务。默认以单进程运行（reload 关闭），Ctrl+C 可干净退出、不残留子进程。

可用环境变量：
    PORT     指定监听端口（默认 8000）
    RELOAD   设为 1/true/yes/on 开启热重载（开发时改代码自动重启；
             注意 Windows 下 reload 会派生子进程，个别情况 Ctrl+C 可能
             未能回收该子进程，生产/演示请用默认关闭）

启动后访问：
    - Swagger UI（在线接口文档 + 调试）: http://localhost:<PORT>/docs
    - ReDoc                              : http://localhost:<PORT>/redoc
    - 健康检查                           : http://localhost:<PORT>/health
"""
import os

import uvicorn

from app.core.logging import setup_logging

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))

# 默认关闭热重载:单进程运行,Ctrl+C 可干净退出、不残留子进程。
# 开发时如需改代码自动重启,设 RELOAD=true 再启动(会派生子进程)。
RELOAD = os.environ.get("RELOAD", "false").lower() in ("1", "true", "yes", "on")


def main():
    setup_logging()
    docs_url = f"http://localhost:{PORT}/docs"
    print("\n" + "=" * 64)
    print("  AI Customer Service 正在启动 ...")
    print(f"  Swagger UI (接口测试):  {docs_url}")
    print(f"  ReDoc              :  http://localhost:{PORT}/redoc")
    print(f"  健康检查           :  http://localhost:{PORT}/health")
    print("=" * 64 + "\n")

    # 不再自动打开浏览器,避免无 GUI / 服务器环境下弹出外部浏览器。
    # 需要查看接口文档时,手动访问下方 docs_url 即可。

    uvicorn.run(
        "app.server:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
    )


if __name__ == "__main__":
    main()
