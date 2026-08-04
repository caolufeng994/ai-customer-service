"""
User model
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    """User account model"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 已废弃: bcrypt 哈希自带 salt, 自定义 salt 列不参与计算。保留为 nullable 仅向后兼容既有库。
    salt: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default=None)
    # 用户角色: "user"=普通用户(仅可使用对话页), "admin"=管理员(可见会话/知识库管理/统计页)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", comment="user=普通用户, admin=管理员")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index('uk_phone', 'phone', unique=True),
        Index('uk_email', 'email', unique=True),
        Index('idx_created_at', 'created_at'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
