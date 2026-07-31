"""
Chat service
"""
from sqlalchemy.orm import Session
from typing import List, Optional
import time
from functools import lru_cache
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.models.message_citation import MessageCitation
from app.models.usage_quota import UsageQuota
from app.schemas.chat import ChatRequest
from app.rag.retriever import Retriever
from app.rag.context_builder import ContextBuilder
from app.rag.prompt_builder import PromptBuilder
from app.rag.llm_client import LLMClient
from app.core.exceptions import ValidationError, QuotaExceededError
from datetime import date
import logging

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_retriever():
    """Get singleton retriever instance"""
    return Retriever(top_k=8, similarity_threshold=0.6)


@lru_cache(maxsize=1)
def get_context_builder():
    """Get singleton context builder instance"""
    return ContextBuilder(max_tokens=2000)


@lru_cache(maxsize=1)
def get_prompt_builder():
    """Get singleton prompt builder instance"""
    return PromptBuilder()


@lru_cache(maxsize=1)
def get_llm_client():
    """Get singleton LLM client instance"""
    return LLMClient()


class ChatService:
    """Chat business logic with RAG pipeline"""
    
    @staticmethod
    def check_quota(db: Session, user_id: int) -> None:
        """Check if user has quota remaining"""
        from datetime import date
        
        # Get or create quota record for today
        quota = db.query(UsageQuota).filter(
            UsageQuota.user_id == user_id,
            UsageQuota.date == date.today()
        ).first()
        
        if not quota:
            quota = UsageQuota(user_id=user_id, date=date.today(), ask_count=0)
            db.add(quota)
            db.commit()
        
        # Check quota limit (default 100 per day)
        if quota.ask_count >= 100:
            raise QuotaExceededError("Daily quota exceeded (100 questions per day)")
    
    @staticmethod
    def increment_quota(db: Session, user_id: int) -> None:
        """Increment user's daily quota"""
        from datetime import date
        from sqlalchemy import and_
        
        quota = db.query(UsageQuota).filter(
            and_(
                UsageQuota.user_id == user_id,
                UsageQuota.date == date.today()
            )
        ).first()
        
        if quota:
            quota.ask_count += 1
            db.commit()
    
    @staticmethod
    def get_conversation_history(db: Session, session_id: int, limit: int = 10) -> List[dict]:
        """Get recent conversation history"""
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.created_at.desc()).limit(limit).all()
        
        # Convert to message format for LLM
        history = []
        for msg in reversed(messages):  # Reverse to get chronological order
            history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return history
    
    @staticmethod
    def create_session_if_needed(db: Session, user_id: int, session_id: Optional[int]) -> SessionModel:
        """Create new session if session_id is None"""
        if session_id:
            session = db.query(SessionModel).filter(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id
            ).first()
            if not session:
                raise ValidationError("Session not found")
            return session
        else:
            session = SessionModel(user_id=user_id, title="新对话")
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
    
    @staticmethod
    def save_user_message(db: Session, session_id: int, content: str) -> Message:
        """Save user message to database"""
        message = Message(
            session_id=session_id,
            role="user",
            content=content
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    @staticmethod
    def save_assistant_message(
        db: Session,
        session_id: int,
        content: str,
        token_in: int,
        token_out: int,
        latency_ms: int,
        finish_reason: str,
        citations: Optional[List[dict]] = None
    ) -> Message:
        """Save assistant message to database"""
        message = Message(
            session_id=session_id,
            role="assistant",
            content=content,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            finish_reason=finish_reason
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        
        # Save citations if provided
        if citations:
            for citation in citations:
                msg_citation = MessageCitation(
                    message_id=message.id,
                    doc_id=citation.get('doc_id', 0),
                    chunk_id=citation.get('chunk_id', ''),
                    score=citation.get('score', 0.0),
                    snippet=citation.get('snippet', '')
                )
                db.add(msg_citation)
            db.commit()
        
        return message
    
    @staticmethod
    def chat_stream(
        db: Session,
        user_id: int,
        request: ChatRequest
    ):
        """
        Stream chat response using RAG pipeline
        Generator that yields SSE events
        """
        start_time = time.time()
        
        # Step 1: Validate and check quota
        if len(request.message) > 500:
            raise ValidationError("Message too long (max 500 characters)")
        
        ChatService.check_quota(db, user_id)
        
        # Step 2: Get or create session
        session = ChatService.create_session_if_needed(db, user_id, request.session_id)
        
        # Step 3: Save user message
        user_message = ChatService.save_user_message(db, session.id, request.message)
        
        # Yield session info
        yield f"data: {ChatService._format_sse_event('session_id', session.id)}\n\n"
        
        # Step 4: Get conversation history
        history = ChatService.get_conversation_history(db, session.id)
        
        # Step 5: RAG pipeline
        try:
            # Retrieve (use singleton)
            retriever = get_retriever()

            # 多轮对话检索优化：当前问题若过短/含指代（如"那会员折扣呢？"），
            # 直接拿原句去向量检索容易因代词缺失而召回失败。这里用上一轮用户
            # 问题做检索_query 改写，提升追问场景的召回率。
            retrieval_query = request.message
            user_turns = [m.get("content", "") for m in history if m.get("role") == "user"]
            if len(user_turns) >= 2 and len(request.message) < 20:
                retrieval_query = f"{user_turns[-2]} {request.message}"

            retrieval_results = retriever.retrieve_with_fallback(retrieval_query, request.kb_id)

            # Build context (use singleton)
            context_builder = get_context_builder()
            context, sources = context_builder.build_context_with_sources(retrieval_results)

            # Build prompt (use singleton)
            prompt_builder = get_prompt_builder()
            if context:
                messages = prompt_builder.build_prompt(request.message, context, history)
                finish_reason = "stop"
            else:
                messages = prompt_builder.build_fallback_prompt(request.message)
                finish_reason = "no_context"

            # Stream LLM response (use singleton)
            llm_client = get_llm_client()
            full_response = ""
            
            yield f"data: {ChatService._format_sse_event('status', 'generating')}\n\n"
            
            try:
                for chunk in llm_client.chat_stream(messages, temperature=0.7, max_tokens=1000):
                    full_response += chunk
                    yield f"data: {ChatService._format_sse_event('content', chunk)}\n\n"
            except Exception as llm_error:
                logger.warning(f"Primary LLM failed, falling back to Ollama: {llm_error}")
                yield f"data: {ChatService._format_sse_event('status', 'switching_to_local_model')}\n\n"
                
                # Fallback to Ollama
                try:
                    fallback_client = llm_client.fallback_to_ollama()
                    full_response = ""
                    for chunk in fallback_client.chat_stream(messages, temperature=0.7, max_tokens=1000):
                        full_response += chunk
                        yield f"data: {ChatService._format_sse_event('content', chunk)}\n\n"
                    finish_reason = "stop_fallback"
                except Exception as fallback_error:
                    logger.error(f"Fallback LLM also failed: {fallback_error}")
                    raise
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Save assistant message
            # Calculate token estimates (approximate: 1 token ≈ 4 characters for Chinese)
            token_in = len(context) // 4 if context else 0
            token_out = len(full_response) // 4
            
            # Build citations with snippets (truncate to 120 chars)
            citations = []
            for result in retrieval_results:
                snippet = result.content[:120]  # Truncate snippet to 120 characters
                citations.append({
                    "doc_id": result.doc_id,
                    "chunk_id": result.chunk_id,
                    "score": float(result.score),
                    "snippet": snippet
                })
            
            assistant_message = ChatService.save_assistant_message(
                db=db,
                session_id=session.id,
                content=full_response,
                token_in=token_in,
                token_out=token_out,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                citations=citations
            )
            
            # Increment quota
            ChatService.increment_quota(db, user_id)
            
            # Update session message count
            session.msg_count += 1
            db.commit()
            
            # Yield completion event
            yield f"data: {ChatService._format_sse_event('done', {'message_id': assistant_message.id, 'finish_reason': finish_reason, 'sources': sources})}\n\n"
            
        except Exception as e:
            logger.error(f"Chat stream failed: {e}")
            yield f"data: {ChatService._format_sse_event('error', str(e))}\n\n"
    
    @staticmethod
    def _format_sse_event(event_type: str, data) -> str:
        """Format SSE event"""
        import json
        return json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
