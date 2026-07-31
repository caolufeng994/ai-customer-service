"""
User model
"""
from sqlalchemy import Column, BigInteger, String, Index
from app.database import Base


class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    phone = Column(String(20), nullable=True, unique=True, index=True)
    email = Column(String(255), nullable=True, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    
    __table_args__ = (
        Index('uk_phone', 'phone', unique=True),
        Index('uk_email', 'email', unique=True),
        Index('idx_created_at', 'created_at'),
    )
