"""
Chat service
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional
import time
import json
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
from app.agent.intent_classifier import IntentClassifier, IntentCategory
from app.agent.router import route, RouteTarget
from app.core.exceptions import ValidationError, QuotaExceededError
from app.core.tracing import span
from app.config import settings
import logging

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_retriever():
    """Get singleton retriever instance"""
    return Retriever(top_k=settings.retrieval_top_k, similarity_threshold=settings.retrieval_threshold)


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
        """
        Check and increment quota atomically using single conditional UPDATE.
        This prevents race conditions in high-concurrency scenarios.
        """
        from sqlalchemy import text

        # Single atomic operation: increment only if under limit
        # Returns rowcount = 1 if successful, 0 if quota exceeded
        result = db.execute(
            text("""
                UPDATE usage_quota
                SET ask_count = ask_count + 1
                WHERE user_id = :user_id
                  AND date = :today
                  AND ask_count < :limit
            """),
            {"user_id": user_id, "today": date.today(), "limit": settings.daily_quota_limit}
        )
        db.commit()

        # If rowcount is 0, either record doesn't exist or quota exceeded
        if result.rowcount == 0:
            # Check if record exists
            quota = db.scalars(
                select(UsageQuota).where(
                    UsageQuota.user_id == user_id,
                    UsageQuota.date == date.today(),
                )
            ).first()

            if not quota:
                # Record doesn't exist, create it with count=1
                quota = UsageQuota(user_id=user_id, date=date.today(), ask_count=1)
                db.add(quota)
                db.commit()
            else:
                # Record exists but quota exceeded
                raise QuotaExceededError(f"Daily quota exceeded ({settings.daily_quota_limit} questions per day)")
    
    @staticmethod
    def increment_quota(db: Session, user_id: int) -> None:
        """
        Increment user's daily quota.
        NOTE: This method is deprecated; check_quota now handles atomic increment.
        Kept for backward compatibility but should not be called.
        """
        # No-op - quota is now incremented atomically in check_quota
        pass
    
    @staticmethod
    def get_conversation_history(db: Session, session_id: int) -> List[dict]:
        """Get recent conversation history"""
        # Calculate limit based on max_history_rounds (each round = 2 messages: user + assistant)
        limit = settings.max_history_rounds * 2
        messages = db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).all()
        
        # Convert to message format for LLM
        history = []
        for msg in reversed(messages):  # Reverse to get chronological order
            history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return history

    @staticmethod
    def get_history(
        db: Session,
        session_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Message]:
        """
        Fetch chat messages for a session (ownership already enforced by the
        caller via SessionService.get_session). Returns messages in
        chronological order, supporting pagination.
        """
        return db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
        ).all()

    @staticmethod
    def create_session_if_needed(db: Session, user_id: int, session_id: Optional[int]) -> SessionModel:
        """Create new session if session_id is None"""
        if session_id:
            session = db.scalars(
                select(SessionModel).where(
                    SessionModel.id == session_id,
                    SessionModel.user_id == user_id,
                )
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
    def _chat_events(db: Session, user_id: int, request: ChatRequest):
        """
        Core RAG pipeline generator shared by both streaming and non-streaming
        endpoints. Yields structured SSE event dicts:
            {"type": "session_id", "data": <int>}
            {"type": "status",     "data": "generating"}
            {"type": "content",    "data": <str chunk>}
            {"type": "done",       "data": {"message_id", "finish_reason", "sources"}}
            {"type": "error",      "data": <str>}
        The assistant message is persisted and quota incremented exactly once,
        regardless of which endpoint consumes the stream.
        """
        start_time = time.time()

        # Step 1: Validate request length.
        # Quota is checked exactly once by the API layer (api/chat.py) before the
        # stream starts, so we must NOT call check_quota again here — doing so
        # would double-increment the daily quota (each question would consume 2 units).
        if len(request.message) > settings.max_question_length:
            raise ValidationError(f"Message too long (max {settings.max_question_length} characters)")

        # Step 2: Get or create session
        session = ChatService.create_session_if_needed(db, user_id, request.session_id)

        # Step 3: Save user message
        user_message = ChatService.save_user_message(db, session.id, request.message)

        # Emit session info
        yield {"type": "session_id", "data": session.id}

        # Step 4: Get conversation history
        history = ChatService.get_conversation_history(db, session.id)

        # 当前问题已作为用户消息入库，会出现在 history 末尾；构造 prompt 历史时
        # 剔除这条刚保存的当前问题，避免它既在历史末尾、又在最终 user message
        # 中重复出现（冗余且浪费 token）。
        prompt_history = (
            history[:-1] if (history and history[-1].get("role") == "user") else history
        )

        # Step 5: 意图识别 + 策略路由（Agent 核心门控层）
        if settings.enable_intent_routing:
            with span("intent_classify") as s_int:
                intent_result = IntentClassifier.classify(request.message)
                intent_category = intent_result.intent
                s_int.set_attribute("intent", intent_category.value)
            with span("route") as s_rt:
                route_target = route(intent_category)
                s_rt.set_attribute("target", route_target.value)
        else:
            # 路由关闭时退化为纯 RAG（兼容单意图 RAG 旧行为），意图仅标记为未知。
            intent_category = IntentCategory.FALLBACK
            route_target = RouteTarget.RAG

        # 将识别到的意图落库到当前用户消息（Message.intent 字段），便于观测与回溯。
        try:
            user_message.intent = intent_category.value
            db.commit()
        except Exception:
            logger.debug("Failed to persist intent on user message", exc_info=False)

        # 初始为空；RAG 路径下会被填充，兜底路径下保持空（不检索、不注入上下文）。
        retrieval_results: list = []
        context = ""
        sources: list = []

        try:
            prompt_builder = get_prompt_builder()

            if route_target == RouteTarget.RAG:
                # Retrieve (use singleton)
                retriever = get_retriever()

                # 多轮对话检索优化：使用 QueryRewriter 替代旧启发式
                from app.framework.memory import QueryRewriter
                retrieval_query = QueryRewriter.rewrite(history, request.message)

                with span("retrieve", attributes={"query": retrieval_query, "kb_id": request.kb_id}) as s_ret:
                    retrieval_results = retriever.retrieve_with_fallback(retrieval_query, request.kb_id)
                    s_ret.set_attribute("result_count", len(retrieval_results))

                # Build context (use singleton)
                context_builder = get_context_builder()
                with span("context_build") as s_ctx:
                    context, sources = context_builder.build_context_with_sources(retrieval_results)
                    s_ctx.set_attribute("chunks", len(retrieval_results))
                    s_ctx.set_attribute("sources", len(sources))

                if context:
                    messages = prompt_builder.build_prompt(request.message, context, prompt_history)
                    finish_reason = "stop"
                else:
                    messages = prompt_builder.build_fallback_prompt(request.message)
                    finish_reason = "no_context"
            else:
                # 兜底/未知意图：直接走无上下文兜底提示，彻底不检索、不注入任何
                # 知识库内容，从路由层杜绝无关内容泄露（与阈值 0.5 形成双保险）。
                logger.info(f"Intent={intent_category.value} routed to FALLBACK (no RAG)")
                messages = prompt_builder.build_fallback_prompt(request.message)
                finish_reason = "fallback"

            # Stream LLM response (use singleton)
            llm_client = get_llm_client()
            full_response = ""

            yield {"type": "status", "data": "generating"}

            with span("llm_generate", attributes={"model": settings.dashscope_model or "unknown"}) as s_llm:
                try:
                    for chunk in llm_client.chat_stream(messages, temperature=0.7, max_tokens=1000):
                        full_response += chunk
                        yield {"type": "content", "data": chunk}
                    s_llm.set_attribute("finish_reason", finish_reason)
                except Exception as llm_error:
                    logger.error(f"LLM generation failed: {llm_error}")
                    s_llm.set_status_error(str(llm_error))
                    # Graceful degradation: return error message instead of raising
                    full_response = "抱歉，服务暂时不可用，请稍后重试。"
                    finish_reason = "error"
                    yield {"type": "content", "data": full_response}

            latency_ms = int((time.time() - start_time) * 1000)

            # Verify citations if context was provided
            if context and settings.enable_citation_verification:
                is_valid, invalid_citations = prompt_builder.verify_citations(full_response, context)
                if not is_valid:
                    logger.warning(f"Invalid citations detected in response: {invalid_citations}")
                    # Note: We still save the response, but log the issue
                    # In production, you might want to trigger a retry or fallback

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

            # Quota was already incremented atomically by the API-layer check_quota
            # call (see api/chat.py). increment_quota is now a deprecated no-op, so
            # it is intentionally not called here.

            # Update session message count
            session.msg_count += 1
            db.commit()

            # Emit completion event
            done_data = {
                "message_id": assistant_message.id,
                "finish_reason": finish_reason,
                "sources": sources,
            }

            # Generate follow-up suggestions (lightweight)
            # Only for successful RAG responses with context
            if finish_reason == "stop" and context and settings.enable_followup_suggestions:
                try:
                    suggestions = ChatService._generate_followup_suggestions(
                        request.message,
                        full_response,
                        llm_client
                    )
                    if suggestions:
                        done_data["suggestions"] = suggestions
                except Exception as e:
                    logger.warning(f"Failed to generate follow-up suggestions: {e}")

            yield {
                "type": "done",
                "data": done_data,
            }

        except Exception as e:
            logger.error(f"Chat pipeline failed: {e}")
            yield {"type": "error", "data": str(e)}

    @staticmethod
    def _generate_followup_suggestions(
        user_query: str,
        assistant_response: str,
        llm_client
    ) -> List[str]:
        """
        Generate lightweight follow-up suggestions
        Uses a simple prompt to generate 2-3 relevant follow-up questions
        """
        prompt = [
            {
                "role": "system",
                "content": "你是一个智能客服助手。根据用户的问题和AI的回答，生成2-3个相关的追问建议。每个建议应该是一个简短的问题，不超过15个字。只返回问题列表，用逗号分隔，不要其他内容。"
            },
            {
                "role": "user",
                "content": f"用户问题：{user_query}\nAI回答：{assistant_response}\n\n请生成2-3个追问建议："
            }
        ]

        try:
            # Use non-streaming for faster response
            result = llm_client.chat(prompt, temperature=0.5, max_tokens=100, stream=False)

            # Parse suggestions (comma-separated)
            suggestions_text = result.strip()
            suggestions = [s.strip() for s in suggestions_text.split(",") if s.strip()]

            # Limit to 3 suggestions
            return suggestions[:3]

        except Exception as e:
            logger.warning(f"Failed to generate follow-up suggestions: {e}")
            return []

    @staticmethod
    async def chat_stream(db: Session, user_id: int, request: ChatRequest):
        """
        Stream chat response using RAG pipeline.
        Returns an async generator that yields SSE-formatted strings
        (``data: {json}\\n\\n``) consumed by FastAPI StreamingResponse.
        """
        for event in ChatService._chat_events(db, user_id, request):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    @staticmethod
    def chat_send(db: Session, user_id: int, request: ChatRequest) -> dict:
        """
        Non-streaming chat: runs the same RAG pipeline as ``chat_stream`` but
        collects the full answer and returns it as a single dict (no SSE).
        Returns:
            {
              "session_id": int,
              "message_id": int,
              "content": str,
              "finish_reason": str,
              "sources": list[dict],
            }
        """
        full_response = ""
        session_id = None
        done_data = None

        for event in ChatService._chat_events(db, user_id, request):
            etype = event.get("type")
            if etype == "session_id":
                session_id = event["data"]
            elif etype == "content":
                full_response += event["data"]
            elif etype == "done":
                done_data = event["data"]
            elif etype == "error":
                # error event carries the failure reason; surface it
                done_data = done_data or {}
                done_data.setdefault("finish_reason", "error")

        if done_data is None:
            done_data = {}

        return {
            "session_id": session_id,
            "message_id": done_data.get("message_id"),
            "content": full_response,
            "finish_reason": done_data.get("finish_reason", "error"),
            "sources": done_data.get("sources", []),
        }
