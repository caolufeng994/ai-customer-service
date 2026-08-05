"""
Chat service
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional
import time
import json
import asyncio
import threading
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
from app.rag.faithfulness import FaithfulnessChecker
from app.agent.intent_classifier import IntentClassifier, IntentCategory
from app.agent.router import route, RouteTarget
from app.core.exceptions import ValidationError, QuotaExceededError
from app.core.tracing import span, get_current_trace_id, set_current_trace_id
from app.database import SessionLocal
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
        citations: Optional[List[dict]] = None,
        grounded: Optional[bool] = None,
        unsupported_claims: Optional[List[str]] = None
    ) -> Message:
        """Save assistant message to database.

        grounded: 防编造自检结果(True/False/None); unsupported_claims: 经判定
        无法被知识库支撑的具体陈述, 以 JSON 文本落库(前端重载时可还原为列表)。
        """
        import json as _json
        message = Message(
            session_id=session_id,
            role="assistant",
            content=content,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            grounded=grounded,
            unsupported_claims=_json.dumps(unsupported_claims, ensure_ascii=False) if unsupported_claims else None
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
    def _chat_events(db: Session, user_id: int, request: ChatRequest, emit_thinking: bool = True):
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

        # —— Agent 思维链(CoT)实时展示:先发出"思考中"状态 ——
        # 在检索开始前立即让用户看到"思考中",后续再用真实检索上下文生成思维链。
        # emit_thinking=False 用于非流式 /send 路径,避免额外 LLM 开销。
        if emit_thinking and settings.enable_thinking_display:
            yield {"type": "thinking_start", "data": {"status": "thinking"}}

        yield {"type": "status", "data": "generating"}

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
            elif route_target == RouteTarget.DIRECT:
                # 闲聊 / 身份 / 越界意图：不检索知识库，由 LLM 直接对话式回答
                # （含机器人身份设定），如「你是谁」「你好」「谢谢」等应给出真实回答，
                # 而非「知识库未检索到」这类仅适用于 RAG 检索为空的兜底话术。
                logger.info(f"Intent={intent_category.value} routed to DIRECT (no RAG, direct LLM answer)")
                messages = prompt_builder.build_direct_prompt(request.message)
                finish_reason = "direct"
            else:
                # 防御性兜底：未知路由目标统一走 DIRECT，避免任何分支遗漏导致 500。
                logger.warning(f"Unknown route_target={route_target.value}, fallback to DIRECT")
                messages = prompt_builder.build_direct_prompt(request.message)
                finish_reason = "direct"

            # Stream LLM response (use singleton)
            llm_client = get_llm_client()
            full_response = ""

            # —— Agent 思维链(CoT)真实流式生成 ——
            # 在检索/路由决策完成后,用真实上下文驱动一次轻量 LLM 推理,
            # 把内部推理过程以 thought 事件流式推给前端,解决"思维链没内容"的问题。
            # 失败仅跳过展示,不阻断正式回答。
            if emit_thinking and settings.enable_thinking_display:
                try:
                    with span(
                        "agent_think",
                        attributes={"intent": intent_category.value, "target": route_target.value},
                    ) as s_think:
                        for think_event in ChatService._stream_thinking(
                            llm_client, request.message, context, intent_category
                        ):
                            yield think_event
                        s_think.set_attribute("emitted", "true")
                except Exception as think_err:
                    logger.warning(f"CoT thinking phase failed (degraded): {think_err}")
                    yield {"type": "thinking_end", "data": {"status": "answering"}}

            # —— 兜底话术(标准、固定、零编造) ——
            # 仅当 RAG 检索为空(no_context, 即知识类意图但知识库无相关片段)时, 不注入任何
            # 知识库上下文、也**不调用 LLM**, 直接以配置中的标准兜底话术作为回答。这样做:
            #   1) 话术固定一致, 不会每次生成不同文案;
            #   2) 彻底杜绝编造(没有任何上下文可供编造);
            #   3) 省去一次 LLM 调用, 降低延迟与成本。
            # 注意: 闲聊/身份/越界意图已被路由到 DIRECT(由 LLM 直接对话式回答), 不会走到这里;
            # 这是「知识库确实没有答案」与「用户没问知识库问题」两种场景的明确区分。
            # thinking 阶段仍照常展示(让前端保持"思考中->回答"的连贯观感)。
            if finish_reason == "no_context":
                full_response = settings.fallback_message
                # finish_reason 保持为路由原因("fallback"/"no_context"), 便于前端/测试区分;
                # 固定兜底话术仅作为响应内容, 不改变 finish_reason 语义。
                for chunk in ChatService._stream_verified_text(full_response):
                    yield {"type": "content", "data": chunk}

                latency_ms = int((time.time() - start_time) * 1000)
                token_out = len(full_response) // 4

                assistant_message = ChatService.save_assistant_message(
                    db=db,
                    session_id=session.id,
                    content=full_response,
                    token_in=0,
                    token_out=token_out,
                    latency_ms=latency_ms,
                    finish_reason=finish_reason,
                    citations=[],
                    # 兜底话术不是基于知识库作答, 标记 grounded=True(无未支撑声明), 无 unsupported_claims。
                    grounded=True,
                    unsupported_claims=[],
                )
                session.msg_count += 1
                db.commit()

                done_data = {
                    "message_id": assistant_message.id,
                    "finish_reason": finish_reason,
                    "sources": [],
                    "grounded": True,
                    "suggestions": [],
                }
                yield {"type": "done", "data": done_data}
                return

            # —— 生成回答(流式直出, 实时推给前端) ——
            # agent 的正式回复在此以"真实流式"方式逐 token 推送给前端: 每个 LLM 输出块
            # 立即作为 content 事件下发, 用户在生成过程中即可看到文字逐块出现, 而非等待
            # 整段生成后再一次性灌出。full_response 同时累积, 用于后续的防编造自检与落库。
            full_response = ""
            with span("llm_generate", attributes={"model": settings.dashscope_model or "unknown"}) as s_llm:
                try:
                    for chunk in llm_client.chat_stream(messages, temperature=0.7, max_tokens=1000):
                        if chunk:
                            full_response += chunk
                            yield {"type": "content", "data": chunk}
                    finish_reason = "stop"
                except Exception as llm_error:
                    logger.error(f"LLM generation failed: {llm_error}")
                    s_llm.set_status_error(str(llm_error))
                    full_response = "抱歉，服务暂时不可用，请稍后重试。"
                    finish_reason = "error"
                    yield {"type": "content", "data": full_response}

            # —— 防编造自检 (Faithfulness Gate, 事后标注) ——
            # 由于回复已实时流式展示, 此处仅做"忠实度判定"并把结果通过 done 事件回传
            # (grounded=false 时前端展示告警), 不再回改已展示文本, 避免"先显示后撤回"的
            # 割裂观感。落库的也保持与展示一致(即流式原文), 保证历史回看与实时一致。
            grounded = True
            unsupported_claims: list = []
            if context and settings.enable_faithfulness_check and finish_reason == "stop":
                try:
                    with span("faithfulness_check") as s_f:
                        checker = FaithfulnessChecker(llm_client, temperature=settings.faithfulness_temperature)
                        verdict = checker.check(full_response, context)
                        s_f.set_attribute("faithful", str(verdict.is_faithful))
                        if not verdict.is_faithful:
                            grounded = False
                            unsupported_claims = verdict.unsupported_claims
                except Exception as fe:
                    logger.warning(f"Faithfulness gate error (degraded to original answer): {fe}")

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

            # Build citations with full original-snippet text.
            # 保留完整原文片段：之前截断到 120 字会导致历史回看时原文引用信息丢失，
            # 违反"输出内容准确反映来源"的要求；此处改为保留完整 chunk 原文。
            citations = []
            for result in retrieval_results:
                snippet = result.content  # 完整原文片段，不再截断
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
                citations=citations,
                grounded=grounded,
                unsupported_claims=unsupported_claims
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
                # 防编造自检结果: grounded=False 表示答案经纠正后仍含无法被知识库
                # 支撑的内容, 前端应展示告警并列出具体陈述, 提示用户谨慎采信。
                "grounded": grounded,
                "unsupported_claims": unsupported_claims,
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
    def _stream_thinking(
        llm_client,
        query: str,
        context: str,
        intent_category,
    ):
        """
        Agent 思维链(Chain-of-Thought)流式生成器。

        产出 SSE 事件流(与 _chat_events 其它事件格式一致):
            {"type": "thinking_start", "data": {"status": "thinking"}}
            {"type": "thought",        "data": "<chunk>"}   (可能多个)
            {"type": "thinking_end",   "data": {"status": "answering"}}

        思考内容由一次轻量 LLM 推理调用驱动,反映 agent 对「用户意图 → 知识库
        检索结果 → 回答规划」的真实推理过程,而非硬编码文案。

        契约:本生成器**绝不向外抛异常**——任何失败都只记录日志并正常发出
        thinking_end,由 _chat_events 的调用方兜底,确保"思考失败"最多只是少一段
        展示,绝不阻断正式回答。
        """
        yield {"type": "thinking_start", "data": {"status": "thinking"}}

        # 如果没有 llm_client（提前调用时），返回简化的思考过程
        if llm_client is None:
            # 简化的思考过程，基于意图分类
            intent_desc = {
                "PRODUCT_CONSULT": "产品咨询",
                "AFTER_SALE": "售后服务",
                "ORDER_QUERY": "订单查询",
                "COMPLAINT": "投诉建议",
                "CHAT": "闲聊",
                "FALLBACK": "未知意图"
            }.get(intent_category.value if intent_category else "FALLBACK", "未知意图")

            simple_thought = f"正在分析用户问题：{query}\n识别到意图：{intent_desc}\n准备检索相关知识库内容..."
            for chunk in simple_thought:
                yield {"type": "thought", "data": chunk}
            yield {"type": "thinking_end", "data": {"status": "answering"}}
            return

        system_prompt = (
            "你是一个智能客服助手的内部「思考过程」生成器。请根据用户的问题"
            "以及(可选的)知识库检索结果,用简洁的中文逐步阐述你的内部推理过程,"
            "例如:1) 理解用户意图;2) 判断知识库中是否存在相关信息;3) 规划回答要点。"
            "只输出推理过程,不要给出最终答案。控制在 3-5 句话,语言自然、口语化。"
        )
        user_content = (
            f"用户问题：{query}\n"
            f"知识库内容：{context if context else '（无相关检索结果）'}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            for chunk in llm_client.chat_stream(
                messages, temperature=0.5, max_tokens=settings.thinking_max_tokens
            ):
                if chunk:
                    yield {"type": "thought", "data": chunk}
        except Exception as e:
            logger.warning(f"Thinking stream interrupted: {e}")
            # 不重新抛出:思考中断即止,直接进入 answering 状态。

        yield {"type": "thinking_end", "data": {"status": "answering"}}

    @staticmethod
    def _stream_verified_text(text: str):
        """
        把"已通过防编造自检"的回答切分为小流式块,
        模拟逐字/逐段实时渲染, 避免短答案一次性出现导致"缺失流式输出"。
        """
        if not text:
            return
        # 按 4 个字符步长切分(中文约 1-2 个词), 兼顾观感与网络开销
        for i in range(0, len(text), 4):
            yield text[i:i + 4]

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
    async def chat_stream(user_id: int, request: ChatRequest):
        """
        Stream chat response using RAG pipeline.
        Returns an async generator that yields SSE-formatted strings
        (``data: {json}\n\n``) consumed by FastAPI StreamingResponse.

        关键修复(为什么之前"没有流式输出"):
        原实现是 `async def` 内用普通 `for` 迭代同步生成器 `_chat_events`, 而
        `_chat_events` 内部通过**同步阻塞 I/O** 调用 LLM
        (`for chunk in llm_client.chat_stream(...)`)。阻塞 I/O 一旦开始(一次生成
        动辄数秒), 事件循环被冻结, `StreamingResponse` 排队等待的 socket 写出一直
        得不到执行, 直到整段生成结束才一次性 flush —— 表现为整段响应在末尾瞬时到达,
        根本没有逐块推流。

        这里用「工作线程 + asyncio.Queue」桥接: 把阻塞的同步生成器放到独立线程跑,
        主事件循环只负责 `await queue.get()` 然后 `yield`。每产生一个事件就能立即
        flush 给前端(session_id / 思考过程 / 正文逐块到达), 事件循环不会再被冻结。
        """
        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue" = asyncio.Queue(maxsize=256)
        sentinel = object()
        stop = threading.Event()

        # 捕获请求线程的 trace_id, 在工作线程中还原, 保证链路追踪可关联到同一次请求。
        parent_trace_id = get_current_trace_id()

        def _produce():
            # 工作线程内使用独立 DB session(SQLAlchemy session 非线程安全,
            # 不能复用请求线程的那个 db)。
            if parent_trace_id:
                set_current_trace_id(parent_trace_id)
            db = SessionLocal()
            try:
                for event in ChatService._chat_events(db, user_id, request):
                    if stop.is_set():
                        break
                    try:
                        # 跨线程把事件推给事件循环侧的队列; 带超时避免客户端断开后
                        # 生产者无限阻塞(背压由 maxsize + 超时共同保证)。
                        asyncio.run_coroutine_threadsafe(
                            queue.put(event), loop
                        ).result(timeout=30)
                    except Exception:
                        break
            except Exception as exc:  # 兜底: 以 error 事件上报, 避免静默断流
                logger.error("[chat_stream] pipeline error: %s", exc, exc_info=True)
                try:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "data": str(exc)}), loop
                    ).result(timeout=5)
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass
                try:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(sentinel), loop
                    ).result(timeout=5)
                except Exception:
                    pass

        worker = threading.Thread(target=_produce, daemon=True)
        worker.start()

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            # 客户端断开时尽快让工作线程退出, 释放其 DB 连接。
            stop.set()

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

        for event in ChatService._chat_events(db, user_id, request, emit_thinking=False):
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
            # 正常 done 事件必带 grounded(bool); 错误路径无 done 数据时缺省 True(无答案则不告警)。
            "grounded": done_data.get("grounded", True),
            "unsupported_claims": done_data.get("unsupported_claims", []),
        }
