"""
Chat API endpoints with SSE streaming and non-streaming send
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatSendResponse
from app.schemas.session import MessageResponse
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse
from app.core.exceptions import BaseAppException
from app.config import settings

router = APIRouter()


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream chat response using RAG pipeline
    Returns SSE (Server-Sent Events) stream
    """
    # Apply rate limiting (both IP-level and global)
    limiter = http_request.app.state.limiter
    # IP-level limit
    await limiter.check(settings.ip_rate_limit, key_func=lambda: http_request.client.host)
    # Global limit
    await limiter.check(settings.global_rate_limit)

    # Pre-validation before entering generator
    if len(request.message) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": f"Message too long (max {settings.max_question_length} characters)"}
        )

    # Check quota before starting stream (dual control with rate limiting)
    try:
        ChatService.check_quota(db, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})

    try:
        return StreamingResponse(
            ChatService.chat_stream(db, current_user.id, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.post("/send", response_model=ApiResponse[ChatSendResponse])
async def chat_send(
    request: ChatRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Non-streaming chat send. Runs the same RAG pipeline as /stream but returns
    the complete assistant reply as a single JSON object instead of SSE.
    """
    # Rate limiting (same policy as /stream)
    limiter = http_request.app.state.limiter
    await limiter.check(settings.ip_rate_limit, key_func=lambda: http_request.client.host)
    await limiter.check(settings.global_rate_limit)

    # Pre-validation
    if len(request.message) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": f"Message too long (max {settings.max_question_length} characters)"}
        )

    # Quota check
    try:
        ChatService.check_quota(db, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})

    try:
        result = ChatService.chat_send(db, current_user.id, request)
        return ApiResponse.ok(
            data=ChatSendResponse(**result),
            message="Message sent successfully"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("/history", response_model=ApiResponse[List[MessageResponse]])
async def get_chat_history(
    session_id: int = Query(..., description="Session ID to fetch messages for"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Max messages to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get chat message history for a session.
    Session ownership is enforced (a user can only read their own sessions).
    """
    try:
        # Verify the session belongs to the current user
        SessionService.get_session(db, session_id, current_user.id)
        messages = ChatService.get_history(
            db, session_id, skip=skip, limit=limit
        )
        return ApiResponse.ok(
            data=[MessageResponse.model_validate(m) for m in messages]
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
