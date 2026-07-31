"""
Session model
"""
from sqlalchemy import Column, BigInteger, String, Integer, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Session(Base):
    """Chat session model"""
    __tablename__ = "sessions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, default="新对话")
    intent_tag = Column(String(50), nullable=True)
    msg_count = Column(Integer, nullable=False, default=0)
    
    # Relationships
    user = relationship("User", backref="sessions")
    messages = relationship("Message", backref="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_user_updated', 'user_id', 'updated_at'),
        Index('idx_intent', 'intent_tag'),
    )
