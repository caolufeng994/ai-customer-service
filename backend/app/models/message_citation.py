"""
Message citation model
"""
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, Text, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MessageCitation(Base):
    """Message citation source model"""
    __tablename__ = "message_citations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index('idx_message', 'message_id'),
        Index('idx_doc', 'doc_id'),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
