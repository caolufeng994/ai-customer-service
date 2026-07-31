"""
Session service
"""
from sqlalchemy.orm import Session
from typing import List
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.models.message_citation import MessageCitation
from app.schemas.session import SessionCreate
from app.core.exceptions import NotFoundError


class SessionService:
    """Session business logic"""
    
    @staticmethod
    def create_session(db: Session, user_id: int, request: SessionCreate) -> SessionModel:
        """Create a new session"""
        session = SessionModel(
            user_id=user_id,
            title=request.title or "新对话"
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    @staticmethod
    def get_user_sessions(db: Session, user_id: int, skip: int = 0, limit: int = 20) -> List[SessionModel]:
        """Get user's sessions with pagination"""
        sessions = db.query(SessionModel).filter(
            SessionModel.user_id == user_id
        ).order_by(SessionModel.updated_at.desc()).offset(skip).limit(limit).all()
        return sessions
    
    @staticmethod
    def get_session(db: Session, session_id: int, user_id: int) -> SessionModel:
        """Get a specific session by ID"""
        session = db.query(SessionModel).filter(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id
        ).first()
        if not session:
            raise NotFoundError("Session not found")
        return session
    
    @staticmethod
    def get_session_messages(db: Session, session_id: int, user_id: int) -> tuple[SessionModel, List[Message]]:
        """Get session with all messages"""
        session = SessionService.get_session(db, session_id, user_id)
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.created_at.asc()).all()
        return session, messages
    
    @staticmethod
    def update_session(db: Session, session_id: int, user_id: int, title: str) -> SessionModel:
        """Update session title"""
        session = SessionService.get_session(db, session_id, user_id)
        session.title = title
        db.commit()
        db.refresh(session)
        return session
    
    @staticmethod
    def delete_session(db: Session, session_id: int, user_id: int) -> None:
        """Delete a session"""
        session = SessionService.get_session(db, session_id, user_id)
        db.delete(session)
        db.commit()
    
    @staticmethod
    def increment_message_count(db: Session, session_id: int) -> None:
        """Increment session message count"""
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session:
            session.msg_count += 1
            db.commit()
