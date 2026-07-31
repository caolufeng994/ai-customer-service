"""
Feedback model
"""
from sqlalchemy import Column, BigInteger, Integer, Text, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Feedback(Base):
    """User feedback model"""
    __tablename__ = "feedbacks"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1 for thumbs up, -1 for thumbs down
    comment = Column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('message_id', 'user_id', name='uk_message_user'),
        Index('idx_user', 'user_id'),
    )
