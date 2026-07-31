"""
Authentication utilities
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_salt() -> str:
    """Generate random salt for password hashing"""
    return secrets.token_hex(32)


def hash_password(password: str, salt: str) -> str:
    """Hash password with salt"""
    # Combine password and salt before hashing
    salted_password = f"{password}{salt}"
    return pwd_context.hash(salted_password)


def verify_password(plain_password: str, salt: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    salted_password = f"{plain_password}{salt}"
    return pwd_context.verify(salted_password, hashed_password)


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
