"""
Feedback schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class FeedbackRequest(BaseModel):
    """Feedback request schema"""
    message_id: int = Field(..., gt=0)
    rating: int = Field(..., ge=-1, le=1)  # -1 (thumbs down), 1 (thumbs up)
    comment: Optional[str] = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    """Feedback response schema"""
    id: int
    message_id: int
    user_id: int
    rating: int
    comment: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True
