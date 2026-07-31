"""
Feedback API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.feedback_service import FeedbackService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse
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
