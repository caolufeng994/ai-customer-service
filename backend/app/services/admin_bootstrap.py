"""
管理员账号引导创建（bootstrap）。

在应用启动时（server.py lifespan）幂等执行：若未配置则跳过；若已存在同邮箱/手机号的
管理员则跳过；否则用配置中的凭据创建一个 role='admin' 的账号。该流程保证系统始终至少有一个
管理员，且普通用户无法通过公开注册接口获得 admin 角色（注册接口强制 role='user'）。

生产环境可将 admin_bootstrap_enabled 设为 false，改为纯手工（脚本/SQL）维护管理员。
"""
import logging
from typing import Optional

from sqlalchemy import or_

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.utils.auth import hash_password

logger = logging.getLogger(__name__)


def ensure_admin(db=None) -> Optional[User]:
    """确保存在一个管理员账号（幂等）。

    Args:
        db: 可选已有 SQLAlchemy Session；为 None 时内部自行创建并关闭。

    Returns:
        新创建的管理员 User 对象，或已存在时返回 None（表示未新建）。
    """
    if not settings.admin_bootstrap_enabled:
        logger.info("admin bootstrap disabled (admin_bootstrap_enabled=false), skip")
        return None

    email = (settings.admin_bootstrap_email or "").strip() or None
    phone = (settings.admin_bootstrap_phone or "").strip() or None
    password = settings.admin_bootstrap_password

    if not email and not phone:
        logger.info("admin bootstrap skipped: no email/phone configured")
        return None
    if not password:
        logger.warning("admin bootstrap skipped: admin_bootstrap_password is empty")
        return None

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        conditions = []
        if email:
            conditions.append(User.email == email)
        if phone:
            conditions.append(User.phone == phone)
        existing = db.query(User).filter(or_(*conditions)).first()
        if existing:
            logger.info("admin account already exists (id=%s), skip bootstrap", existing.id)
            return None

        password_hash = hash_password(password)
        admin = User(
            phone=phone,
            email=email,
            password_hash=password_hash,
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        logger.info("admin bootstrap: created admin account (id=%s, email=%s)", admin.id, email)
        return admin
    except Exception as e:  # pragma: no cover - 依赖实时 DB, 启动期尽力而为
        logger.warning("admin bootstrap failed (non-fatal): %s", e)
        if own_session:
            db.rollback()
        return None
    finally:
        if own_session:
            db.close()
