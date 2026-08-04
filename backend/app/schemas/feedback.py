"""
Feedback schemas
"""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class FeedbackRequest(BaseModel):
    """Feedback request schema"""
    message_id: int = Field(..., gt=0)
    rating: int = Field(..., ge=-1, le=1)  # -1 (thumbs down), 1 (thumbs up)
    comment: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=32)  # 结构化反馈原因(可选): 答非所问/事实错误/没召回/太啰嗦/其他


class FeedbackResponse(BaseModel):
    """Feedback response schema"""
    id: int
    message_id: int
    user_id: int
    rating: int
    comment: Optional[str]
    reason: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class AdminFeedbackItem(BaseModel):
    """管理后台反馈明细（含关联上下文富化字段）"""
    id: int
    message_id: int
    user_id: int
    rating: int
    comment: Optional[str]
    reason: Optional[str]
    created_at: datetime
    # 富化上下文
    session_id: Optional[int] = None
    session_title: Optional[str] = None
    user_account: Optional[str] = None          # 用户邮箱或手机号
    message_content: Optional[str] = None       # 被评价的消息正文（通常是对话的回答）
    message_role: Optional[str] = None

    class Config:
        from_attributes = True


class AdminFeedbackSummary(BaseModel):
    """管理后台反馈汇总统计"""
    total: int
    like_count: int
    dislike_count: int
    by_reason: dict                            # 原因 -> 数量

    class Config:
        from_attributes = True
