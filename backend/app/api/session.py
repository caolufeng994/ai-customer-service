"""
Session API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.session import SessionCreate, SessionUpdate, SessionResponse, SessionDetailResponse, MessageResponse
from app.services.session_service import SessionService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse, PaginatedResponse
from app.core.exceptions import BaseAppException
from app.core.tracing import span

router = APIRouter()


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def get_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's sessions with pagination"""
    with span("list_sessions", attributes={"user_id": current_user.id}):
        try:
            sessions = SessionService.get_user_sessions(db, current_user.id, skip, limit)
            total = len(sessions)  # In production, use COUNT query
            return PaginatedResponse.ok(
                data=[SessionResponse.model_validate(s) for s in sessions],
                total=total,
                page=skip // limit + 1,
                page_size=limit
            )
        except BaseAppException as e:
            raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.post("", response_model=ApiResponse[SessionResponse])
async def create_session(
    request: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new session"""
    try:
        session = SessionService.create_session(db, current_user.id, request)
        return ApiResponse.ok(
            data=SessionResponse.model_validate(session),
            message="Session created successfully"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("/{session_id}", response_model=ApiResponse[SessionDetailResponse])
async def get_session_detail(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get session detail with all messages"""
    try:
        session, messages = SessionService.get_session_messages(db, session_id, current_user.id)
        # 详情接口的 msg_count 直接由实际消息列表长度派生,
        # 避免与冗余计数器(session.msg_count)失同步。
        session_resp = SessionResponse.model_validate(session).model_copy(
            update={"msg_count": len(messages)}
        )
        return ApiResponse.ok(
            data=SessionDetailResponse(
                session=session_resp,
                messages=[MessageResponse.model_validate(m) for m in messages]
            )
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.put("/{session_id}", response_model=ApiResponse[SessionResponse])
async def update_session(
    session_id: int,
    payload: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update session title (via JSON body)"""
    try:
        session = SessionService.update_session(db, session_id, current_user.id, payload.title)
        return ApiResponse.ok(
            data=SessionResponse.model_validate(session),
            message="Session updated successfully"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.delete("/{session_id}", response_model=ApiResponse)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a session"""
    try:
        SessionService.delete_session(db, session_id, current_user.id)
        return ApiResponse.ok(message="Session deleted successfully")
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
