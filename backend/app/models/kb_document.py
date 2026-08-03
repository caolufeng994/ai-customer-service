"""
Knowledge base document model
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, String, Integer, Enum, Text, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class KbDocument(Base):
    """Knowledge base document model"""
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True,
                                                  comment="Owning user; enables per-user KB isolation")
    kb_id: Mapped[str] = mapped_column(String(50), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(Enum('txt', 'md', 'pdf', name='file_type'), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum('processing', 'ready', 'failed', 'deleting', name='doc_status'),
        nullable=False,
        default="processing",
    )
    error_msg: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    chunks: Mapped[List["KbChunk"]] = relationship(
        "KbChunk", backref="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_kb_status', 'kb_id', 'status'),
        Index('idx_created', 'created_at'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
