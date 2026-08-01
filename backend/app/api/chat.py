"""
Chat API endpoints with SSE streaming
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.utils.dependencies import get_current_user
from app.models.user import User
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
