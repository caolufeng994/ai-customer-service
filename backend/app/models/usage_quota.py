"""
Usage quota model
"""
from sqlalchemy import Column, BigInteger, Integer, Date, UniqueConstraint, ForeignKey
from app.database import Base


class UsageQuota(Base):
    """Daily usage quota tracking model"""
    __tablename__ = "usage_quota"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    ask_count = Column(Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uk_user_date'),
    )
