"""
Authentication utilities
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from app.config import settings

# 直接基于 bcrypt 库做哈希，避免 passlib 与 bcrypt 4.x 的兼容性问题（Python 3.13 环境下常见）
# bcrypt 哈希结果自带 salt，无需额外维护自定义 salt 列。


# bcrypt only considers the first 72 bytes of a password. Longer inputs raise
# `ValueError: password too long` (which previously surfaced as HTTP 500 on
# registration). Truncate to 72 bytes so that any password length is accepted,
# matching bcrypt's documented semantics and the register schema (max_length=100).
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hash password using bcrypt.

    bcrypt 会在结果中嵌入自己的 salt，无需也不应额外拼接自定义 salt。
    此前实现把 64 字符 hex salt 拼到密码后，会导致超过 bcrypt 72 字节上限，
    使注册/登录失败。这里仅对密码做哈希，并截断到 bcrypt 的 72 字节上限。
    """
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        pw = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed_password.encode("utf-8"))
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
