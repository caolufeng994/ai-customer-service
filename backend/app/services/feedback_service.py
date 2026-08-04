"""
Feedback service
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Tuple
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.session import Session as SessionModel
from app.models.user import User
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
            comment=request.comment,
            reason=request.reason
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
    def count_feedbacks(
        db: Session,
        user_id: int,
        rating: Optional[int] = None
    ) -> int:
        """Total count of the current user's feedback (honors the same rating filter).

        Used to populate the paginated response's ``meta.total``/``total_pages`` so
        they reflect the full result set rather than just the current page.
        """
        query = db.query(Feedback).filter(Feedback.user_id == user_id)
        if rating is not None:
            query = query.filter(Feedback.rating == rating)
        return query.count()

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

    @staticmethod
    def list_all_feedbacks(
        db: Session,
        *,
        skip: int = 0,
        limit: int = 20,
        rating: Optional[int] = None,
        reason: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> Tuple[List[dict], int]:
        """管理后台：跨用户列出全量反馈，支持多维度筛选 + 关联上下文富化。

        富化字段通过 join Message(拿 session_id/正文) -> Session(标题) 与 User(账号)
        得到，单条记录即携带「被评价回答 + 所属会话 + 提交用户」上下文，便于管理员
        直接定位失败 case。返回 (items, total)。
        """
        query = (
            db.query(
                Feedback,
                Message.session_id,
                Message.content.label("message_content"),
                Message.role.label("message_role"),
                SessionModel.title.label("session_title"),
                User.email,
                User.phone,
            )
            .join(Message, Feedback.message_id == Message.id)
            .outerjoin(SessionModel, Message.session_id == SessionModel.id)
            .outerjoin(User, Feedback.user_id == User.id)
        )

        if rating is not None:
            query = query.filter(Feedback.rating == rating)
        if reason is not None:
            query = query.filter(Feedback.reason == reason)
        if keyword:
            # 关键词模糊匹配用户填写的文字反馈
            query = query.filter(Feedback.comment.like(f"%{keyword}%"))
        if start_date:
            # 起始日 00:00:00；日期字符串与 DateTime 列按 ISO 字典序比较
            query = query.filter(Feedback.created_at >= start_date)
        if end_date:
            # 含当天: 截止日 23:59:59
            query = query.filter(Feedback.created_at <= f"{end_date} 23:59:59")

        total = query.count()

        sort_col = getattr(Feedback, sort_by, Feedback.created_at)
        if order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        rows = query.offset(skip).limit(limit).all()

        items: List[dict] = []
        for f, session_id, message_content, message_role, session_title, email, phone in rows:
            items.append({
                "id": f.id,
                "message_id": f.message_id,
                "user_id": f.user_id,
                "rating": f.rating,
                "comment": f.comment,
                "reason": f.reason,
                "created_at": f.created_at,
                "session_id": session_id,
                "session_title": session_title,
                "user_account": email or phone,
                "message_content": message_content,
                "message_role": message_role,
            })
        return items, total

    @staticmethod
    def feedback_summary(db: Session) -> dict:
        """管理后台反馈汇总：总数 / 点赞 / 点踩 / 按原因分布（reason->数量）。"""
        total = db.query(Feedback).count()
        like_count = db.query(Feedback).filter(Feedback.rating == 1).count()
        dislike_count = db.query(Feedback).filter(Feedback.rating == -1).count()
        by_reason: dict = {}
        for r, c in (
            db.query(Feedback.reason, func.count(Feedback.id))
            .group_by(Feedback.reason)
            .all()
        ):
            key = r if r else "(未选择)"
            by_reason[key] = c
        return {
            "total": total,
            "like_count": like_count,
            "dislike_count": dislike_count,
            "by_reason": by_reason,
        }
