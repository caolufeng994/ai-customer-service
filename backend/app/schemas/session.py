"""
Session schemas
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import json
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
    grounded: Optional[bool] = None
    unsupported_claims: Optional[List[str]] = None
    created_at: datetime

    @field_validator("unsupported_claims", mode="before")
    @classmethod
    def _parse_unsupported_claims(cls, v):
        # 落库时为 JSON 文本, 此处还原为列表(list[str]); 已为列表则原样返回。
        if isinstance(v, str) and v:
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return v

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
