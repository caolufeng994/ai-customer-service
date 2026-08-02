"""
Chat schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    """Chat request schema"""
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=500)
    kb_id: str = "default"


class ChatMessage(BaseModel):
    """Chat message schema"""
    role: str
    content: str


class ChatSource(BaseModel):
    """Retrieval source cited by an assistant answer"""
    doc_id: int
    doc_name: Optional[str] = None
    chunk_id: str
    score: float


class ChatSendResponse(BaseModel):
    """Non-streaming chat send response schema"""
    session_id: Optional[int] = None
    message_id: Optional[int] = None
    content: str
    finish_reason: str  # stop | no_context | error
    sources: List[ChatSource] = []
