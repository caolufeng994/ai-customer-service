"""
Message model
"""
from sqlalchemy import Column, BigInteger, String, Integer, Text, Enum, DateTime, func, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Message(Base):
    """Chat message model"""
    __tablename__ = "messages"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum('user', 'assistant', name='message_role'), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    token_in = Column(Integer, nullable=False, default=0)
    token_out = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    finish_reason = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    citations = relationship("MessageCitation", backref="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_session_created', 'session_id', 'created_at'),
    )
