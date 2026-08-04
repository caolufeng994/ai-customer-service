"""
FastAPI dependencies
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError
from app.database import get_db
from app.utils.auth import decode_access_token
from app.models.user import User
from app.core.exceptions import AuthenticationError

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user"""
    # 缺失凭证时显式返回 401(FastAPI HTTPBearer 默认是 403,不符合 REST 规范)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_ERROR", "message": "Missing or invalid authentication token"},
        )
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        
        if payload is None:
            raise AuthenticationError("Invalid token")
        
        user_id = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token")
        
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise AuthenticationError("User not found")
        
        return user
        
    except JWTError:
        raise AuthenticationError("Invalid token")
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": e.code, "message": e.message}
        )


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency to get current authenticated admin user.

    普通用户(role != 'admin')访问受保护的管理接口时返回 403 FORBIDDEN。
    与 get_current_user 复用同一套鉴权, 仅多一层角色校验。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "需要管理员权限"},
        )
    return current_user
