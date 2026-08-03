"""
意图识别 + 策略路由 单元测试。

覆盖：
  * 7 类业务意图分类正确（与 qa_set.json category 对齐）
  * 越界/闲聊/未知 query → 兜底闲聊(FALLBACK)
  * 置信度阈值：仅命中低频闲聊词(权重<阈值) → FALLBACK
  * 路由映射：知识类 → RAG，兜底/未知 → FALLBACK
  * 边界：空字符串 → FALLBACK；路由为纯函数无循环
"""
import pytest

from app.agent.intent_classifier import IntentClassifier, IntentCategory, _score_intent
from app.agent.router import route, RouteTarget, KNOWLEDGE_INTENTS


# 各意图代表 query（取自 qa_set.json 业务分布）
CASES = [
    ("你们的产品有哪些核心功能？", IntentCategory.PRODUCT),
    ("这个系统能帮企业做什么？", IntentCategory.PRODUCT),
    ("基础版价格是多少？", IntentCategory.PRICING),
    ("有没有免费试用？", IntentCategory.PRICING),
    ("怎么申请退款？", IntentCategory.REFUND),
    ("退款一般多久到账？", IntentCategory.REFUND),
    ("怎么注册一个新账号？", IntentCategory.ACCOUNT),
    ("忘记密码了怎么办？", IntentCategory.ACCOUNT),
    ("怎么往知识库上传文档？", IntentCategory.KB_DOC),
    ("支持哪些文件格式？", IntentCategory.KB_DOC),
    ("怎么查询我的订单？", IntentCategory.ORDER),
    ("在哪里查看物流信息？", IntentCategory.ORDER),
]

OUT_OF_SCOPE = [
    "今天天气怎么样？",      # 越界
    "你是谁？",              # 闲聊（命中你是谁权重1.5 → 仍归 FALLBACK 分类，但属兜底意图）
    "帮我写首诗",            # 完全无关
    "asdfqwerty",            # 乱码/未知
]


@pytest.mark.parametrize("query,expected", CASES)
def test_classify_knowledge_intents(query, expected):
    res = IntentClassifier.classify(query)
    assert res.intent == expected, f"{query} => {res.intent.value}, expected {expected.value}"
    assert res.confidence >= 1.0  # 至少命中一个有效业务词


@pytest.mark.parametrize("query", OUT_OF_SCOPE)
def test_classify_out_of_scope_fallback(query):
    res = IntentClassifier.classify(query)
    assert res.intent == IntentCategory.FALLBACK


def test_empty_query_fallback():
    assert IntentClassifier.classify("").intent == IntentCategory.FALLBACK
    assert IntentClassifier.classify("   ").intent == IntentCategory.FALLBACK


def test_score_intent_no_double_count():
    # "核心功能" 不应同时被 "核心功能"(1.5) 与 "功能"(1.0) 重复计分。
    score = _score_intent("核心功能", {"核心功能": 1.5, "功能": 1.0})
    assert score == 1.5


def test_router_knowledge_to_rag():
    for intent in KNOWLEDGE_INTENTS:
        assert route(intent) == RouteTarget.RAG


def test_router_fallback_and_unknown():
    assert route(IntentCategory.FALLBACK) == RouteTarget.FALLBACK
    # 任何非知识类（含未来新增枚举）都应收敛到 FALLBACK，无遗漏分支。
    # 通过"知识类之外必为 FALLBACK"不变量验证：
    all_intents = set(IntentCategory)
    for intent in all_intents:
        target = route(intent)
        if intent in KNOWLEDGE_INTENTS:
            assert target == RouteTarget.RAG
        else:
            assert target == RouteTarget.FALLBACK


def test_router_is_pure_function():
    # 多次调用结果一致（无状态、无循环）。
    assert route(IntentCategory.ORDER) is route(IntentCategory.ORDER)
    assert route(IntentCategory.FALLBACK) is route(IntentCategory.FALLBACK)


# --------------------------------------------------------------------------- #
# 集成测试：越界 query（天气）应被路由到兜底，且完全不触发 RAG 检索。
# --------------------------------------------------------------------------- #
class _SpyRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve_with_fallback(self, query, kb_id="default", user_id=None):
        self.calls += 1
        return []  # 即便被错误调用也返回空，避免误判


class _FakeLLMClient:
    def chat_stream(self, messages, temperature=0.7, max_tokens=1000):
        for chunk in ["抱歉", "，我暂无法回答该问题。"]:
            yield chunk


def test_out_of_scope_skips_rag(client, monkeypatch):
    from tests.helpers import register_and_login, auth_headers
    import app.services.chat_service as cs
    from app.core.exceptions import QuotaExceededError

    creds = register_and_login(client, email="router@example.com")
    h = auth_headers(creds["token"])

    spy = _SpyRetriever()
    monkeypatch.setattr(cs, "get_retriever", lambda: spy)
    monkeypatch.setattr(cs, "get_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setattr(cs.ChatService, "check_quota", staticmethod(lambda db, uid: None))

    r = client.post("/api/chat/send", json={"message": "今天天气怎么样？"}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["finish_reason"] == "fallback"
    assert spy.calls == 0, "越界 query 不应触发 RAG 检索"
    assert data["sources"] == []


def test_knowledge_query_uses_rag(client, monkeypatch):
    from tests.helpers import register_and_login, auth_headers
    import app.services.chat_service as cs

    creds = register_and_login(client, email="router2@example.com")
    h = auth_headers(creds["token"])

    spy = _SpyRetriever()
    monkeypatch.setattr(cs, "get_retriever", lambda: spy)
    monkeypatch.setattr(cs, "get_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setattr(cs.ChatService, "check_quota", staticmethod(lambda db, uid: None))

    r = client.post("/api/chat/send", json={"message": "怎么申请退款？"}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["finish_reason"] in ("stop", "no_context")
    assert spy.calls == 1, "知识类 query 应触发一次 RAG 检索"
