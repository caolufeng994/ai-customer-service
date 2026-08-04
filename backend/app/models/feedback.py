"""
Feedback model
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Integer, Text, String, DateTime, func, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Feedback(Base):
    """User feedback model"""
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 for thumbs up, -1 for thumbs down
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )  # 结构化反馈原因: 答非所问/事实错误/没召回/太啰嗦/其他; 便于失败 case 归类分析
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('message_id', 'user_id', name='uk_message_user'),
        Index('idx_user', 'user_id'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
