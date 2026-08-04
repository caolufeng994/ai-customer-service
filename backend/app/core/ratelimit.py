"""
Shared slowapi rate limiter instance.

Defined in its own module (instead of inside app.server) so that routers
such as app.api.chat can import the limiter without triggering a circular
import: app.server imports the routers at the bottom, after the FastAPI app
is created, while this module only depends on slowapi.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func defaults to the client's remote address. Per the project config
# this is used for both the per-IP limit and the (per-IP) global limit.
#
# config_filename=os.devnull: slowapi 内部用 starlette.Config 读取 .env, 而
# starlette 在 Windows 上默认以系统编码(gbk)打开文件。一旦 .env 含 UTF-8 中文
# 注释就会触发 UnicodeDecodeError, 导致服务启动即崩溃(见项目 .env 第25行注释)。
# 本项目限流配置全部通过构造参数与 @limiter.limit 装饰器指定, 不依赖 .env,
# 故指向空设备跳过该读取 —— 既修复 Windows 启动崩溃, 又保留真实环境变量
# (通过 os.environ) 对 slowapi 的生效。
limiter = Limiter(
    key_func=get_remote_address,
    config_filename=os.devnull,
)
