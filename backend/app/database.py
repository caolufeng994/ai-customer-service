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
