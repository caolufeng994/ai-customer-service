"""
Feedback service
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.feedback import Feedback
from app.models.message import Message
from app.schemas.feedback import FeedbackRequest
from app.core.exceptions import NotFoundError, ValidationError
import logging

logger = logging.getLogger(__name__)


class FeedbackService:
    """Feedback business logic"""
    
    @staticmethod
    def submit_feedback(db: Session, user_id: int, request: FeedbackRequest) -> Feedback:
        """Submit feedback for a message"""
        # Verify message exists
        message = db.query(Message).filter(Message.id == request.message_id).first()
        if not message:
            raise NotFoundError("Message not found")
        
        # Check if user already submitted feedback for this message
        existing = db.query(Feedback).filter(
            Feedback.message_id == request.message_id,
            Feedback.user_id == user_id
        ).first()
        
        if existing:
            raise ValidationError("Feedback already submitted for this message")
        
        # Create feedback
        feedback = Feedback(
            message_id=request.message_id,
            user_id=user_id,
            rating=request.rating,
            comment=request.comment
        )
        
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        
        logger.info(f"User {user_id} submitted feedback for message {request.message_id}: rating={request.rating}")
        return feedback

    @staticmethod
    def get_feedbacks(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        rating: Optional[int] = None
    ) -> List[Feedback]:
        """List feedback submitted by the current user (newest first), optional rating filter."""
        query = db.query(Feedback).filter(Feedback.user_id == user_id)
        if rating is not None:
            query = query.filter(Feedback.rating == rating)
        return (
            query.order_by(Feedback.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_feedback(db: Session, feedback_id: int, user_id: int) -> Feedback:
        """Get a single feedback by ID, scoped to the current user."""
        feedback = db.query(Feedback).filter(
            Feedback.id == feedback_id,
            Feedback.user_id == user_id
        ).first()
        if not feedback:
            raise NotFoundError("Feedback not found")
        return feedback

    @staticmethod
    def delete_feedback(db: Session, feedback_id: int, user_id: int) -> None:
        """Delete a feedback by ID, scoped to the current user."""
        feedback = FeedbackService.get_feedback(db, feedback_id, user_id)
        db.delete(feedback)
        db.commit()
