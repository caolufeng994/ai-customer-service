"""
Chat API endpoints with SSE streaming and non-streaming send
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatSendResponse
from app.schemas.session import MessageResponse
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse
from app.core.exceptions import BaseAppException, NotFoundError
from app.core.ratelimit import limiter
from app.config import settings

router = APIRouter()

# Rate limit applied via slowapi's decorator (the only correct public API).
# slowapi has no `limiter.check` method, so the previous `await limiter.check(...)`
# calls raised AttributeError -> HTTP 500 on every request.
# Both the per-IP limit and the global limit are applied here as a single
# semicolon-separated string (stacking two @limiter.limit decorators would
# drop the `request` parameter signature and fail at import time).
_CHAT_RATE_LIMIT = f"{settings.ip_rate_limit};{settings.global_rate_limit}"


async def _safe_stream(db: Session, user_id: int, payload: ChatRequest):
    """Wrap the RAG streaming generator so the DB session is always closed.

    For a ``StreamingResponse`` FastAPI's dependency teardown (``db.close()`` in
    the ``get_db`` generator) is not reliably invoked once the stream starts,
    which would leak the DB connection (and its open transaction -> metadata
    lock) until garbage collection. Closing the session explicitly here keeps
    the pool healthy in both production and tests. A later redundant
    ``db.close()`` from FastAPI's teardown is a harmless no-op.
    """
    try:
        async for chunk in ChatService.chat_stream(db, user_id, payload):
            yield chunk
    finally:
        db.close()


@router.post("/stream")
@limiter.limit(_CHAT_RATE_LIMIT)
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream chat response using RAG pipeline
    Returns SSE (Server-Sent Events) stream
    """
    # Pre-validation before entering generator
    if len(payload.message) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": f"Message too long (max {settings.max_question_length} characters)"}
        )

    # Check quota before starting stream (dual control with rate limiting)
    try:
        ChatService.check_quota(db, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})

    # Pre-validate referenced session so a missing session returns a clean 400
    # (ValidationError) instead of failing mid-stream.
    if payload.session_id is not None:
        try:
            SessionService.get_session(db, payload.session_id, current_user.id)
        except NotFoundError:
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION_ERROR", "message": "Session not found"}
            )

    try:
        return StreamingResponse(
            _safe_stream(db, current_user.id, payload),
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
@limiter.limit(_CHAT_RATE_LIMIT)
async def chat_send(
    payload: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Non-streaming chat send. Runs the same RAG pipeline as /stream but returns
    the complete assistant reply as a single JSON object instead of SSE.
    """
    # Pre-validation
    if len(payload.message) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": f"Message too long (max {settings.max_question_length} characters)"}
        )

    # Quota check
    try:
        ChatService.check_quota(db, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})

    # Pre-validate referenced session (clean 400 instead of generator error)
    if payload.session_id is not None:
        try:
            SessionService.get_session(db, payload.session_id, current_user.id)
        except NotFoundError:
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION_ERROR", "message": "Session not found"}
            )

    try:
        result = ChatService.chat_send(db, current_user.id, payload)
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
