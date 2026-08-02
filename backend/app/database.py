"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

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
