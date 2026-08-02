"""
Feedback API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.feedback_service import FeedbackService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse, PaginatedResponse
from app.core.exceptions import BaseAppException

router = APIRouter()


@router.post("", response_model=ApiResponse[FeedbackResponse])
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for a message"""
    try:
        feedback = FeedbackService.submit_feedback(db, current_user.id, request)
        return ApiResponse.ok(
            data=FeedbackResponse.model_validate(feedback),
            message="Feedback submitted successfully"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("", response_model=PaginatedResponse[FeedbackResponse])
async def list_feedback(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Max items per page"),
    rating: Optional[int] = Query(None, ge=-1, le=1, description="Filter by rating: -1 / 0 / 1"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List feedback submitted by the current user (with pagination + rating filter)"""
    try:
        items = FeedbackService.get_feedbacks(db, current_user.id, skip, limit, rating)
        total = len(items)  # In production, use a COUNT query
        return PaginatedResponse.ok(
            data=[FeedbackResponse.model_validate(f) for f in items],
            total=total,
            page=skip // limit + 1,
            page_size=limit
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("/{feedback_id}", response_model=ApiResponse[FeedbackResponse])
async def get_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single feedback by ID (scoped to the current user)"""
    try:
        feedback = FeedbackService.get_feedback(db, feedback_id, current_user.id)
        return ApiResponse.ok(data=FeedbackResponse.model_validate(feedback))
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.delete("/{feedback_id}", response_model=ApiResponse)
async def delete_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a feedback by ID (scoped to the current user)"""
    try:
        FeedbackService.delete_feedback(db, feedback_id, current_user.id)
        return ApiResponse.ok(message="Feedback deleted successfully")
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
