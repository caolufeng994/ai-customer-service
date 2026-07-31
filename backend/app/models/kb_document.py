"""
Knowledge base document model
"""
from sqlalchemy import Column, BigInteger, String, Integer, BigInteger as BigInt, Enum, Text, DateTime, func, Index
from sqlalchemy.orm import relationship
from app.database import Base


class KbDocument(Base):
    """Knowledge base document model"""
    __tablename__ = "kb_documents"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(String(50), nullable=False, default="default")
    name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(Enum('txt', 'md', 'pdf', name='file_type'), nullable=False)
    size = Column(BigInt, nullable=False)
    char_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    status = Column(Enum('processing', 'ready', 'failed', 'deleting', name='doc_status'), nullable=False, default="processing")
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    chunks = relationship("KbChunk", backref="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_kb_status', 'kb_id', 'status'),
        Index('idx_created', 'created_at'),
    )
