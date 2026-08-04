"""
Authentication schemas
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    """Registration request schema"""
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6, max_length=100)
    
    def validate_phone_or_email(self):
        """Ensure at least one of phone or email is provided"""
        if not self.phone and not self.email:
            raise ValueError("Either phone or email must be provided")
        return self


class LoginRequest(BaseModel):
    """Login request schema"""
    phone_or_email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=100)


class TokenResponse(BaseModel):
    """Token response schema"""
    token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """User response schema"""
    id: int
    phone: Optional[str]
    email: Optional[str]
    role: str = "user"   # user=普通用户, admin=管理员
    created_at: datetime
    
    class Config:
        from_attributes = True
