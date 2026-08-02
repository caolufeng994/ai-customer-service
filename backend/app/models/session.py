"""
Session model
"""
from datetime import datetime
from typing import List
from sqlalchemy import BigInteger, String, Integer, DateTime, func, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Session(Base):
    """Chat session model"""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新对话")
    intent_tag: Mapped[str] = mapped_column(String(50), nullable=True)
    msg_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="sessions")
    messages: Mapped[List["Message"]] = relationship(
        "Message", backref="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_user_updated', 'user_id', 'updated_at'),
        Index('idx_intent', 'intent_tag'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
