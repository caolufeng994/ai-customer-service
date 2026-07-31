"""
Feedback service
"""
from sqlalchemy.orm import Session
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
