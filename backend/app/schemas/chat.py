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
