"""
Session service
"""
import re
import logging
from sqlalchemy.orm import Session
from typing import List
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.schemas.session import SessionCreate
from app.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)

# 智能标题生成提示词: 要求 LLM 基于对话上下文产出 ≤15 字、点明核心主题的标题,
# 避免元描述词与冗余标点, 且只输出标题本身(便于前端直接落库)。
_TITLE_PROMPT = """你是一个专业的客服对话标题生成器。请根据下面的对话内容，生成一句简洁、准确概括对话核心主题的中文标题。

要求：
1. 长度不超过 15 个汉字
2. 直接点明用户咨询的核心问题或主题，避免空泛
3. 不要包含"会话""对话""用户""助手""AI""客服"等元描述词
4. 不要使用引号、书名号、句号
5. 只输出标题本身，不要任何解释或前缀

对话内容：
{context}"""


class SessionService:
    """Session business logic"""
    
    @staticmethod
    def create_session(db: Session, user_id: int, request: SessionCreate) -> SessionModel:
        """Create a new session"""
        # Keep an explicitly-empty title as-is; only default when omitted (None).
        title = request.title if request.title is not None else "新对话"
        session = SessionModel(
            user_id=user_id,
            title=title
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    @staticmethod
    def get_user_sessions(db: Session, user_id: int, skip: int = 0, limit: int = 20) -> List[SessionModel]:
        """Get user's sessions with pagination"""
        sessions = db.query(SessionModel).filter(
            SessionModel.user_id == user_id
        ).order_by(SessionModel.updated_at.desc()).offset(skip).limit(limit).all()
        return sessions
    
    @staticmethod
    def get_session(db: Session, session_id: int, user_id: int) -> SessionModel:
        """Get a specific session by ID"""
        session = db.query(SessionModel).filter(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id
        ).first()
        if not session:
            raise NotFoundError("Session not found")
        return session
    
    @staticmethod
    def get_session_messages(db: Session, session_id: int, user_id: int) -> tuple[SessionModel, List[Message]]:
        """Get session with all messages"""
        session = SessionService.get_session(db, session_id, user_id)
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.created_at.asc()).all()
        return session, messages
    
    @staticmethod
    def update_session(db: Session, session_id: int, user_id: int, title: str) -> SessionModel:
        """Update session title"""
        session = SessionService.get_session(db, session_id, user_id)
        session.title = title
        db.commit()
        db.refresh(session)
        return session
    
    @staticmethod
    def delete_session(db: Session, session_id: int, user_id: int) -> None:
        """Delete a session"""
        session = SessionService.get_session(db, session_id, user_id)
        db.delete(session)
        db.commit()
    
    @staticmethod
    def generate_session_title(db: Session, session_id: int, user_id: int) -> SessionModel:
        """根据会话上下文用 LLM 生成会话标题, 写回数据库。

        行为:
        - 无用户消息时不生成(保持原标题, 通常仍是"新对话")。
        - LLM 失败或无结果时回退到首条用户消息的启发式标题。
        - 生成的标题与原标题一致时跳过写库, 避免冗余更新(随上下文稳定后不再抖动)。
        """
        session, messages = SessionService.get_session_messages(db, session_id, user_id)
        context = _extract_title_context(messages)
        if not context:
            return session
        raw = _build_title_with_llm(context)
        first_user = next((m.content for m in messages if m.role == "user"), "")
        title = _clean_title(raw) or _heuristic_title(first_user)
        if title and title != session.title:
            session.title = title
            db.commit()
            db.refresh(session)
        return session

    @staticmethod
    def increment_message_count(db: Session, session_id: int) -> None:
        """Increment session message count"""
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session:
            session.msg_count += 1
            db.commit()


# ---------------------------------------------------------------------------
# 智能标题生成辅助函数(模块级, 便于独立测试)
# ---------------------------------------------------------------------------

def _extract_title_context(messages: List[Message]) -> str:
    """从对话记录中提炼标题生成所需的上下文: 首条用户问题 + 首条助手回答 + 最新用户追问。"""
    user_msgs = [m for m in messages if m.role == "user"]
    asst_msgs = [m for m in messages if m.role == "assistant"]
    if not user_msgs:
        return ""
    first_user = (user_msgs[0].content or "").strip()
    first_asst = (asst_msgs[0].content if asst_msgs else "").strip()
    last_user = (user_msgs[-1].content or "").strip()
    parts = [f"用户：{first_user[:200]}"]
    if first_asst:
        parts.append(f"助手：{first_asst[:300]}")
    # 话题可能在中途转移, 引入最新用户追问让标题随上下文动态更新
    if last_user and last_user != first_user:
        parts.append(f"用户（最新）：{last_user[:200]}")
    return "\n".join(parts)


def _build_title_with_llm(context: str) -> str:
    """调用 LLM 生成标题; 任何异常(无 API key / 网络/解析)都返回空串交由回退逻辑处理。"""
    try:
        from app.rag.llm_client import LLMClient

        client = LLMClient()
        result = client.chat(
            [
                {"role": "system", "content": "你是一个简洁专业的对话标题生成器。"},
                {"role": "user", "content": _TITLE_PROMPT.format(context=context)},
            ],
            temperature=0.3,
            max_tokens=40,
            stream=False,
        )
        return (result or "").strip()
    except Exception as e:
        logger.warning(f"LLM 标题生成失败, 回退启发式: {e}")
        return ""


def _clean_title(raw: str) -> str:
    """清洗 LLM 输出: 去掉前缀/引号/书名号/首尾标点, 折叠空白, 防御性截断。"""
    if not raw:
        return ""
    t = raw.strip()
    t = re.sub(r"^\s*标题\s*[:：]\s*", "", t)  # 去掉可能的"标题："前缀
    # 去除各类引号/书名号(含中文弯引号与方头括号), 避免模型输出被标点包裹
    _QUOTE_CHARS = (
        '"\'`'
        "\u201c\u201d\u2018\u2019"          # “ ” ‘ ’
        "\u300c\u300d\u300e\u300f"          # 「 」 『 』
        "\u300a\u300b\u3010\u3011"          # 《 》 【 】
        "\u3014\u3015"                       # 〔 〕
        "[]"
    )
    for ch in _QUOTE_CHARS:
        t = t.replace(ch, "")
    t = t.strip(" 。.，,！!？?；;：:、\n\r\t")
    t = re.sub(r"\s+", " ", t)
    return t[:20] if len(t) > 20 else t


def _heuristic_title(first_user: str) -> str:
    """兜底标题: 首条用户消息前 20 字(当前系统自动起标题的同款逻辑)。"""
    trimmed = re.sub(r"\s+", " ", (first_user or "").strip())
    if not trimmed:
        return "新对话"
    return trimmed[:20] + ("…" if len(trimmed) > 20 else "")
