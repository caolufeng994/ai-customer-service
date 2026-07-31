"""
Knowledge base chunk model
"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, Index, ForeignKey, UniqueConstraint
from app.database import Base


class KbChunk(Base):
    """Knowledge base text chunk model"""
    __tablename__ = "kb_chunks"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doc_id = Column(BigInteger, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    vector_id = Column(String(100), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('vector_id', name='uk_vector'),
        Index('idx_doc_chunk', 'doc_id', 'chunk_index'),
    )
