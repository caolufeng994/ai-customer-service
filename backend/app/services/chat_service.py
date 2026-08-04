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
from app.rag.faithfulness import FaithfulnessChecker
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

            # —— Agent 思维链(Chain-of-Thought)实时展示 ——
            # 在正式回答前,先让 agent 把"思考过程"流式推给前端:
            #   thinking_start (状态:思考中)
            #   thought       (思维链内容,逐块流式)
            #   thinking_end  (状态切换:开始回答)
            # 思考阶段由一次轻量 LLM 推理调用驱动,失败仅跳过展示、不阻断主链路。
            # emit_thinking=False 用于非流式 /send 路径,避免额外 LLM 开销。
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
                    logger.warning(f"CoT thinking phase failed (degraded to direct answer): {think_err}")

            yield {"type": "status", "data": "generating"}

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

            # —— 生成回答(先缓冲, 再做防编造自检, 最后才把"已验证"内容推给前端) ——
            # 采用"拦截式": 用户看到的回答一定经过忠实度校验/纠正, 避免先显编造再撤回。
            raw_chunks = []
            with span("llm_generate", attributes={"model": settings.dashscope_model or "unknown"}) as s_llm:
                try:
                    for chunk in llm_client.chat_stream(messages, temperature=0.7, max_tokens=1000):
                        raw_chunks.append(chunk)
                    full_response = "".join(raw_chunks)
                    finish_reason = "stop"
                except Exception as llm_error:
                    logger.error(f"LLM generation failed: {llm_error}")
                    s_llm.set_status_error(str(llm_error))
                    full_response = "抱歉，服务暂时不可用，请稍后重试。"
                    finish_reason = "error"

            # —— 防编造自检 (Faithfulness Gate) ——
            # 在把答案发给用户前, 比对"回答"与"召回上下文"的事实一致性;
            # 不忠实则触发基于 [K] 内容的自我纠正并复检, 仍不通过则标记 grounded=False。
            grounded = True
            unsupported_claims: list = []
            if context and settings.enable_faithfulness_check and finish_reason == "stop":
                try:
                    with span("faithfulness_check") as s_f:
                        checker = FaithfulnessChecker(llm_client, temperature=settings.faithfulness_temperature)
                        verdict = checker.check(full_response, context)
                        s_f.set_attribute("faithful", str(verdict.is_faithful))
                        if not verdict.is_faithful:
                            candidate = full_response
                            for _ in range(settings.faithfulness_max_correct):
                                fixed = checker.correct(candidate, context, verdict.unsupported_claims)
                                if not fixed:
                                    break
                                recheck = checker.check(fixed, context)
                                s_f.set_attribute("recheck_faithful", str(recheck.is_faithful))
                                candidate = fixed
                                if recheck.is_faithful:
                                    break
                            final_verdict = checker.check(candidate, context)
                            if not final_verdict.is_faithful:
                                grounded = False
                                unsupported_claims = verdict.unsupported_claims
                            # 不论是否完全忠实, 都用"最后一次纠正版"(至少已剔除被标记的陈述)
                            full_response = candidate
                except Exception as fe:
                    logger.warning(f"Faithfulness gate error (degraded to original answer): {fe}")

            # 把最终(已验证/已纠正)回答流式推给前端, 保留逐行流式观感
            for chunk in ChatService._stream_verified_text(full_response):
                yield {"type": "content", "data": chunk}

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
        把"已通过防编造自检"的回答切分为流式块(按换行 + 超长行再切分),
        用于模拟逐字流式推送, 兼顾"拦截式校验"与"流式观感"。
        """
        if not text:
            return
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            if line:
                # 超长行按字符再切分, 避免单块过大
                for i in range(0, len(line), 80):
                    yield line[i:i + 80]
            if idx != len(lines) - 1:
                yield "\n"

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
