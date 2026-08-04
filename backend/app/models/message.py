"""
Message model
"""
from datetime import datetime
from typing import List
from typing import Optional
from sqlalchemy import BigInteger, String, Integer, Text, Enum, DateTime, Boolean, func, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Message(Base):
    """Chat message model"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Enum('user', 'assistant', name='message_role'), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=True)
    token_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finish_reason: Mapped[str] = mapped_column(String(50), nullable=True)
    # 防编造自检结果落库: grounded=False 表示答案经纠正后仍含无法被知识库支撑的内容;
    # unsupported_claims 为被判定为不可靠的具体陈述(JSON 文本)。二者仅对 assistant 消息有意义。
    grounded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    unsupported_claims: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    citations: Mapped[List["MessageCitation"]] = relationship(
        "MessageCitation", backref="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_session_created', 'session_id', 'created_at'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
