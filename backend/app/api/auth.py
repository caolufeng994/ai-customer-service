"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse
from app.services.auth_service import AuthService
from app.utils.auth import get_token_expires_in
from app.core.response import ApiResponse
from app.core.exceptions import BaseAppException

router = APIRouter()


@router.post("/register", response_model=ApiResponse[UserResponse])
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        user = AuthService.register(db, request)
        return ApiResponse.ok(
            data=UserResponse.model_validate(user),
            message="Registration successful"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.post("/login", response_model=ApiResponse[dict])
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login user and return access token"""
    try:
        user, token = AuthService.login(db, request)
        return ApiResponse.ok(
            data={
                "token": token,
                "token_type": "bearer",
                "expires_in": get_token_expires_in(),  # derived from jwt_expire_hours
                "user": UserResponse.model_validate(user).model_dump()
            },
            message="Login successful"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
