"""
意图识别模块（Intent Recognition）

将用户 query 归类为评测集 qa_set.json 定义的 7 类业务意图之一：
    产品咨询 / 价格套餐 / 退款售后 / 账号登录 / 知识库文档 / 订单 / 兜底闲聊

设计说明
--------
* 主分类器：确定性「规则 + 加权词典」分类器。
  - 零额外 LLM 调用（满足 AI架构设计.md 的成本控制原则），延迟可预测。
  - 采用「最长匹配优先 + 非重叠区间」打分，避免子串重复计分导致误判。
* 可选 LLM 兜底：当规则置信度低于阈值且开启 `intent_fallback_to_llm` 时，
  才调用一次 LLM 做结构化意图判定；默认关闭。
* 未命中 / 低置信：统一归为 `兜底闲聊`（FALLBACK），由路由层走兜底提示。

为何不用纯 LLM 分类
-------------------
1) 每次对话多一次 LLM 往返，增加延迟与成本；
2) 确定性规则对高频业务词（退货/退款/登录/价格…）召回稳定、可测试；
3) 与现有「单意图 RAG」架构兼容，作为门控层而非独立子系统。
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class IntentCategory(str, Enum):
    """业务意图枚举，与 qa_set.json 的 category 字段对齐。"""
    PRODUCT = "产品咨询"
    PRICING = "价格套餐"
    REFUND = "退款售后"
    ACCOUNT = "账号登录"
    KB_DOC = "知识库文档"
    ORDER = "订单"
    # 兜底：闲聊 / 越界 / 未知。所有未命中或低置信 query 的归宿。
    FALLBACK = "兜底闲聊"


# 关键词词典：意图 -> {关键词: 权重}。
# 越具体/越长的短语权重越高，降低误召回；通用词权重低，避免"产品"等字眼
# 在无关句里被触发。权重设计围绕 intent_confidence_threshold=1.0：
# 命中任一有效业务词(权重>=1)即可越过阈值；纯闲聊/越界词权重偏低或不达阈值。
INTENT_LEXICON: Dict[IntentCategory, Dict[str, float]] = {
    IntentCategory.PRODUCT: {
        "核心功能": 1.5, "功能": 1.0, "产品": 1.0, "系统": 0.8, "企业": 0.6,
        "做什么": 1.2, "能干": 1.0, "能力": 1.0, "支持哪些语言": 1.2, "语言": 0.8,
        "接入": 1.0, "对接": 1.0, "API": 1.2, "接口": 0.8, "移动端": 1.2,
        "App": 1.0, "客户端": 0.9, "帮你": 0.8, "帮助": 0.6, "智能客服": 1.0,
    },
    IntentCategory.PRICING: {
        "价格": 1.5, "多少钱": 1.5, "收费": 1.3, "费用": 1.2, "套餐": 1.5,
        "版本": 1.0, "免费": 1.2, "试用": 1.3, "基础版": 1.5, "专业版": 1.5,
        "企业版": 1.5, "定价": 1.3, "按月": 1.0, "年付": 1.0, "多少钱一个月": 1.5,
    },
    IntentCategory.REFUND: {
        "退货": 1.8, "退款": 1.8, "退换": 1.6, "换货": 1.4, "售后": 1.5,
        "维修": 1.3, "保修": 1.3, "无理由": 1.5, "七天": 1.4, "7天": 1.4,
        "到账": 1.4, "申请退款": 1.6, "质量问题": 1.3, "退钱": 1.5, "退订": 1.3,
    },
    IntentCategory.ACCOUNT: {
        "注册": 1.6, "登录": 1.6, "登陆": 1.5, "账号": 1.2, "账户": 1.2,
        "密码": 1.5, "忘记密码": 1.8, "找回密码": 1.8, "重置密码": 1.8,
        "手机号": 1.0, "手机": 0.6, "邮箱": 1.0, "注销": 1.3, "绑定": 1.0,
    },
    IntentCategory.KB_DOC: {
        "知识库": 1.8, "上传文档": 1.8, "上传": 1.2, "文档": 1.2, "文件": 1.0,
        "格式": 1.2, "txt": 1.0, "pdf": 1.0, "md": 1.0, "向量化": 1.5,
        "处理中": 1.3, "导入": 1.2, "批量导入": 1.4, "分词": 1.0,
    },
    IntentCategory.ORDER: {
        "订单": 1.8, "下单": 1.6, "物流": 1.6, "快递": 1.5, "配送": 1.4,
        "发货": 1.4, "查订单": 1.8, "我的订单": 1.8, "修改订单": 1.6,
        "取消订单": 1.6, "运单": 1.4, "收货": 1.0,
    },
    # 兜底闲聊：权重整体偏低；仅靠这些词通常达不到阈值 1.0，触发 FALLBACK。
    IntentCategory.FALLBACK: {
        "你是谁": 1.5, "你叫什么": 1.5, "你好": 0.8, "您好": 0.8, "谢谢": 0.6,
        "感谢": 0.6, "聊聊": 0.8, "闲聊": 1.2, "天气": 0.4, "今天": 0.3,
        "开心": 0.6, "难过": 0.6, "心情": 0.5,
    },
}


class IntentResult:
    """单次意图识别结果。"""

    def __init__(
        self,
        intent: IntentCategory,
        confidence: float,
        scores: Optional[Dict[str, float]] = None,
        method: str = "rule",
    ):
        self.intent = intent
        self.confidence = confidence
        self.scores = scores or {}
        self.method = method

    def to_dict(self) -> Dict[str, object]:
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 3),
            "method": self.method,
            "scores": {k.value: round(v, 3) for k, v in self.scores.items()},
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"IntentResult(intent={self.intent.value}, confidence={self.confidence:.2f}, method={self.method})"


def _score_intent(text: str, keywords: Dict[str, float]) -> float:
    """对单个意图按「最长匹配优先 + 非重叠区间」加权打分。

    避免「核心功能」同时匹配「核心功能」(1.5) 与「功能」(1.0) 造成重复计分。
    返回该意图的累计权重分。
    """
    score = 0.0
    consumed: List[Tuple[int, int]] = []
    # 词越长、权重越高越优先，先消耗高价值匹配。
    for kw, w in sorted(keywords.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            end = idx + len(kw)
            overlap = any(not (end <= s or idx >= e) for (s, e) in consumed)
            if not overlap:
                score += w
                consumed.append((idx, end))
                start = end
            else:
                start = idx + 1
    return score


class IntentClassifier:
    """意图识别器（规则主分类 + 可选 LLM 兜底）。"""

    @staticmethod
    def classify(text: str) -> IntentResult:
        """分类用户 query，返回 IntentResult。

        阈值逻辑：
        - 任一知识类意图加权分 >= `intent_confidence_threshold` → 采纳该意图；
        - 否则（含仅命中 FALLBACK 低频词）→ 归为 FALLBACK（兜底闲聊）。
        """
        if not text or not text.strip():
            return IntentResult(IntentCategory.FALLBACK, 0.0, method="empty")

        scores = {
            intent: _score_intent(text, keywords)
            for intent, keywords in INTENT_LEXICON.items()
        }

        # 取分数最高的意图（FALLBACK 也参与，保证"无更优者则兜底"）。
        best_intent = max(scores, key=lambda i: scores[i])
        best_score = scores[best_intent]

        threshold = settings.intent_confidence_threshold

        # 低于阈值 → 兜底（含完全无命中 best_score==0）。
        if best_score < threshold:
            return IntentResult(IntentCategory.FALLBACK, best_score, scores, method="rule")

        # 规则已达成置信度，直接返回。
        if not settings.intent_fallback_to_llm:
            return IntentResult(best_intent, best_score, scores, method="rule")

        # 可选：LLM 兜底二次判定（仅当开启）。
        llm_intent = IntentClassifier._llm_fallback(text)
        if llm_intent is not None:
            return IntentResult(llm_intent, best_score, scores, method="llm")
        return IntentResult(best_intent, best_score, scores, method="rule")

    @staticmethod
    def _llm_fallback(text: str) -> Optional[IntentCategory]:
        """调用 LLM 做结构化意图判定；失败或解析异常时返回 None（回退规则结果）。"""
        try:
            from app.rag.llm_client import LLMClient
            from app.agent.router import KNOWLEDGE_INTENTS  # noqa: F401 (文档/覆盖用)

            valid = "/".join([i.value for i in IntentCategory])
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是意图分类器。仅从给定列表中选择一个最贴合用户问题的意图，"
                        f"直接输出该意图名称，不要解释。可选：{valid}。"
                    ),
                },
                {"role": "user", "content": text},
            ]
            client = LLMClient()
            raw = client.chat(messages, temperature=0.0, max_tokens=20) or ""
            raw = raw.strip().strip("\"'")
            for intent in IntentCategory:
                if intent.value == raw:
                    return intent
            return None
        except Exception as e:  # pragma: no cover - 网络/外部依赖
            logger.warning(f"LLM intent fallback failed: {e}")
            return None
