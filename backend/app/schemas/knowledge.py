"""
Knowledge base schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentResponse(BaseModel):
    """Document response schema"""
    id: int
    kb_id: str
    name: str
    file_type: str
    size: int
    char_count: int
    chunk_count: int
    status: str
    error_msg: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    """Document upload response schema"""
    document_id: int
    status: str
    message: str
