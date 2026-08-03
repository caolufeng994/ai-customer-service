"""
一键启动入口（开发 / 演示）

在 backend/ 目录下执行：

    python main.py

即可启动"后端 + 知识库"两条链路：本入口会强制开启 AUTO_INIT_KB，
在 lifespan 阶段把 seed_docs/ 下的预置文档向量化进 Chroma（幂等，已 ready
的会跳过），从而一条命令完成后端服务初始化与知识库就绪，无需再手动跑
init_kb.py。前端则另开一个终端执行 `npm run dev`（见 frontend 目录）。

默认以单进程运行（reload 关闭），Ctrl+C 可干净退出、不残留子进程。

注意:必须在 import 任何 app 模块之前设置 AUTO_INIT_KB。app.config 在首次
被 import 时会实例化 Settings 单例并固定 auto_init_kb 的值;若在该单例创建
之后才设置环境变量,则不会生效。pytest 不走本入口,.env 中 AUTO_INIT_KB 保持
false,因此不会在测试里触发网络 embedding。
"""
import os

# 若项目 .env 自带 DASHSCOPE_API_KEY,则清除可能由外部环境(例如运行时注入的
# 临时变量)设置的同名变量,避免无效/临时的系统级 key 覆盖项目自身的密钥,
# 确保本项目始终使用 .env 中的 key。仅当 .env 里确实有该字段时才清除。
# 注意:.env 与本文件(main.py)同目录(backend/),不是项目根目录。
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, encoding="utf-8") as _f:
        for _line in _f:
            if _line.strip().startswith("DASHSCOPE_API_KEY="):
                os.environ.pop("DASHSCOPE_API_KEY", None)
                break

# 必须在 import 任何 app 模块之前设置(见模块 docstring 说明)。
# 这样 `python main.py` 一条命令即完成后端 + 知识库启动。
os.environ["AUTO_INIT_KB"] = "true"

import uvicorn

from app.core.logging import setup_logging
from app.config import settings  # 复用同一 settings 单例,lifespan 读到的是同一个对象

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))

# 默认关闭热重载:单进程运行,Ctrl+C 可干净退出、不残留子进程。
# 开发时如需改代码自动重启,设 RELOAD=true 再启动(会派生子进程)。
RELOAD = os.environ.get("RELOAD", "false").lower() in ("1", "true", "yes", "on")


def main():
    # 双保险:无论 import 顺序如何,确保知识库自动初始化开启。
    settings.auto_init_kb = True

    log_config = setup_logging()
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
        log_config=log_config,
    )


if __name__ == "__main__":
    main()
