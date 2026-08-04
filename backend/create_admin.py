"""
手动创建/确保管理员账号。

用法（在 backend/ 目录下）:
    python create_admin.py

逻辑与 server 启动期引导完全一致（ensure_admin 幂等）：
- 若未配置 email/phone 或密码为空则跳过；
- 若同邮箱/手机号的管理员已存在则跳过；
- 否则用 .env 中的 admin_bootstrap_* 凭据创建一个 role='admin' 账号。

适合在 DB 已就绪但服务尚未启动、或想立即创建管理员时运行。
"""
import os
import sys

# 让脚本能直接 import app.*
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    # 在导入 app 前确保 .env 已被 pydantic-settings 加载（import app.config 即触发）。
    from app.database import init_db
    from app.services.admin_bootstrap import ensure_admin

    # 先确保表结构最新(幂等补齐 users.role 等列), 否则旧库会报 Unknown column 'role'。
    init_db()
    admin = ensure_admin()
    if admin is None:
        print(
            "未创建新管理员（已存在 / 未配置 admin_bootstrap_email|phone|password / 已禁用）。\n"
            "如需创建，请在 backend/.env 中设置:\n"
            "  ADMIN_BOOTSTRAP_ENABLED=true\n"
            "  ADMIN_BOOTSTRAP_EMAIL=admin@example.com\n"
            "  ADMIN_BOOTSTRAP_PHONE=13800000000   # 可选\n"
            "  ADMIN_BOOTSTRAP_PASSWORD=Admin@123456"
        )
    else:
        print(f"管理员账号已创建: id={admin.id} email={admin.email} phone={admin.phone}")


if __name__ == "__main__":
    main()
