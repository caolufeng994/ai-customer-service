"""
Authentication utilities
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from app.config import settings

# 直接基于 bcrypt 库做哈希，避免 passlib 与 bcrypt 4.x 的兼容性问题（Python 3.13 环境下常见）


def generate_salt() -> str:
    """Generate random salt for password hashing"""
    return secrets.token_hex(32)


def hash_password(password: str, salt: str) -> str:
    """Hash password with salt"""
    # Combine password and salt before hashing
    salted_password = f"{password}{salt}".encode("utf-8")
    return bcrypt.hashpw(salted_password, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, salt: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    salted_password = f"{plain_password}{salt}".encode("utf-8")
    try:
        return bcrypt.checkpw(salted_password, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


def get_token_expires_in() -> int:
    """Get token expiration time in seconds"""
    return settings.jwt_expire_hours * 3600
