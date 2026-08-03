"""
Session schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SessionCreate(BaseModel):
    """Session creation request schema"""
    title: Optional[str] = Field(None, max_length=255)


class SessionUpdate(BaseModel):
    """Session update request schema (rename)"""
    title: str = Field(..., max_length=255)


class SessionResponse(BaseModel):
    """Session response schema"""
    id: int
    user_id: int
    title: str
    intent_tag: Optional[str]
    msg_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Message response schema"""
    id: int
    session_id: int
    role: str
    content: str
    intent: Optional[str]
    token_in: int
    token_out: int
    latency_ms: int
    finish_reason: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageCitationResponse(BaseModel):
    """Message citation response schema"""
    id: int
    message_id: int
    doc_id: int
    chunk_id: str
    score: float
    snippet: str
    
    class Config:
        from_attributes = True


class SessionDetailResponse(BaseModel):
    """Session detail with messages response schema"""
    session: SessionResponse
    messages: list[MessageResponse]
