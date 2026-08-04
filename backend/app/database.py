"""
Database connection and session management
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.debug
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for getting database session
    Used in FastAPI endpoints
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables. Call this on application startup.

    Imports every model so all tables are registered on Base.metadata,
    then creates any missing tables (idempotent). The target database is
    MySQL and must already exist — this function only manages table schema,
    not the database itself.
    """
    # 注册全部模型,确保 create_all 能建出所有表
    from app.models import (  # noqa: F401
        User, Session, Message, MessageCitation,
        KbDocument, KbChunk, Feedback, UsageQuota,
    )

    Base.metadata.create_all(bind=engine)

    # 为已存在的 messages 表补充防编造自检列(grounded / unsupported_claims)。
    # create_all 不会 ALTER 既有表, 故此处做幂等补齐; 新库由 create_all 直接建好, 此处为 no-op。
    # 该步骤非致命: 失败仅告警, 不影响其余启动流程。
    _ensure_message_faithfulness_columns(engine)

    # 为已存在的 users 表补充 role 列(普通用户/管理员权限区分)。
    # 同上: 既有表需要幂等 ALTER 补齐; 新库由 create_all 直接建好, 此处为 no-op。
    _ensure_user_role_column(engine)

    # 把已存在的 users.salt 列改为 nullable(bcrypt 自带 salt, 自定义 salt 已废弃)。
    # 既有 NOT NULL 列需幂等 ALTER, 否则不再写 salt 的新注册会插入失败; 新库为 no-op。
    _ensure_user_salt_nullable(engine)


def _ensure_message_faithfulness_columns(engine):
    """幂等补齐 messages 表的防编造自检列; 非致命, 失败仅记录告警。

    仅在列不存在时执行 ALTER, 已存在则跳过。兼容 MySQL(text 列存 JSON 字符串)。
    """
    try:
        with engine.connect() as conn:
            schema = conn.exec_driver_sql("SELECT DATABASE()").scalar()
            if not schema:
                return
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'messages'",
                (schema,),
            ).fetchall()
            existing = {r[0] for r in rows}
            # (列名, DDL): 仅在缺失时补齐
            needed = {
                "grounded": "ALTER TABLE messages ADD COLUMN grounded TINYINT(1) NULL",
                "unsupported_claims": "ALTER TABLE messages ADD COLUMN unsupported_claims TEXT NULL",
            }
            for col, ddl in needed.items():
                if col not in existing:
                    conn.exec_driver_sql(ddl)
                    conn.commit()
                    logger.info(f"Migrated messages table: added column '{col}'")
    except Exception as e:  # pragma: no cover - 尽力而为, 不影响启动
        logger.warning(f"Skipped messages-column migration (non-fatal): {e}")


def _ensure_user_role_column(engine):
    """幂等补齐 users 表的 role 列(普通用户/管理员权限区分); 非致命, 失败仅记录告警。

    仅在列不存在时执行 ALTER(带 DEFAULT 'user'), 已存在则跳过。兼容 MySQL。
    """
    try:
        with engine.connect() as conn:
            schema = conn.exec_driver_sql("SELECT DATABASE()").scalar()
            if not schema:
                return
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'",
                (schema,),
            ).fetchall()
            existing = {r[0] for r in rows}
            if "role" not in existing:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                )
                conn.commit()
                logger.info("Migrated users table: added column 'role'")
    except Exception as e:  # pragma: no cover - 尽力而为, 不影响启动
        logger.warning(f"Skipped users-column migration (non-fatal): {e}")


def _ensure_user_salt_nullable(engine):
    """幂等把 users.salt 列改为 nullable(bcrypt 自带 salt, 自定义 salt 已废弃); 非致命。

    仅在 salt 列存在时执行 ALTER MODIFY 为 NULL, 不存在则跳过(新库无此列)。
    确保不再写 salt 的新注册/管理员引导不会因 NOT NULL 约束插入失败。
    """
    try:
        with engine.connect() as conn:
            schema = conn.exec_driver_sql("SELECT DATABASE()").scalar()
            if not schema:
                return
            rows = conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'",
                (schema,),
            ).fetchall()
            existing = {r[0] for r in rows}
            if "salt" in existing:
                conn.exec_driver_sql(
                    "ALTER TABLE users MODIFY COLUMN salt VARCHAR(64) NULL"
                )
                conn.commit()
                logger.info("Migrated users table: salt column set to nullable (deprecated)")
    except Exception as e:  # pragma: no cover - 尽力而为, 不影响启动
        logger.warning(f"Skipped users.salt-nullable migration (non-fatal): {e}")
