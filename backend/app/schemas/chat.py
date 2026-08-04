"""
Chat schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    """Chat request schema"""
    session_id: Optional[int] = None
    # 注意: 不在此处设 max_length。超长消息由端点的 max_question_length(500)
    # 校验返回 400 INVALID_REQUEST; 若在此设 max_length=500, Pydantic 会先于
    # 端点返回 422, 与文档/接口设计不一致。
    message: str = Field(..., min_length=1)
    kb_id: str = "default"


class ChatMessage(BaseModel):
    """Chat message schema"""
    role: str
    content: str


class ChatSource(BaseModel):
    """Retrieval source cited by an assistant answer.

    与答案中的 [K编号] 严格一一对应: k_index=1 即答案里 [K1] 所指代的来源。
    """
    doc_id: int
    doc_name: Optional[str] = None
    chunk_id: str
    chunk_index: Optional[int] = None
    k_index: Optional[int] = None   # 与上下文 [K编号] 对齐
    score: float
    snippet: Optional[str] = None


class ChatSendResponse(BaseModel):
    """Non-streaming chat send response schema"""
    session_id: Optional[int] = None
    message_id: Optional[int] = None
    content: str
    finish_reason: str  # stop | no_context | error
    sources: List[ChatSource] = []
    grounded: bool = True  # 防编造自检: False=经纠正仍含无法被知识库支撑的内容
    unsupported_claims: List[str] = []
