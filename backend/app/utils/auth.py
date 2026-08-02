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
    """Hash password.

    注意:bcrypt 会在结果中嵌入自己的 salt,无需再拼接自定义 salt。
    此前实现把 64 字符 hex salt 拼到密码后,导致输入超过 bcrypt 72 字节上限,
    使所有注册/登录失败。这里仅对密码做哈希,自定义 salt 列仅作记录保留。
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, salt: str, hashed_password: str) -> bool:
    """Verify password against hash (salt 参数保留以兼容调用点,不参与计算)"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
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
