"""
Message citation model
"""
from sqlalchemy import Column, BigInteger, String, Numeric, Text, Index, ForeignKey
from app.database import Base


class MessageCitation(Base):
    """Message citation source model"""
    __tablename__ = "message_citations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    doc_id = Column(BigInteger, nullable=False)
    chunk_id = Column(String(100), nullable=False)
    score = Column(Numeric(5, 4), nullable=False)
    snippet = Column(Text, nullable=False)
    
    __table_args__ = (
        Index('idx_message', 'message_id'),
        Index('idx_doc', 'doc_id'),
    )
