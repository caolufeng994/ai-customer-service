"""
Knowledge base chunk model
"""
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, Text, DateTime, func, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class KbChunk(Base):
    """Knowledge base text chunk model"""
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('vector_id', name='uk_vector'),
        Index('idx_doc_chunk', 'doc_id', 'chunk_index'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
