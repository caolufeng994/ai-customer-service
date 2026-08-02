"""
Usage quota model
"""
from datetime import date, datetime
from sqlalchemy import BigInteger, Integer, Date, DateTime, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class UsageQuota(Base):
    """Daily usage quota tracking model"""
    __tablename__ = "usage_quota"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    ask_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uk_user_date'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
