"""
回归测试:崩溃修复项 + 响应格式合规性。

覆盖:
  * SC03 会话空标题保留(不再被默认成"新对话")
  * KL02 知识库按用户隔离(列表 / 按 id 获取 / 删除)
  * 聊天会话预校验:引用不存在的 session -> 400 VALIDATION_ERROR(而非流式中途报错)
  * 错误响应格式统一为 {"detail": {code, message}};422 仍为 Pydantic 数组
  * 配额 429 / 限流 429 的格式合规
  * 跨用户越权访问(会话/知识/反馈)返回 404
"""
import asyncio
import json

from tests.helpers import register_and_login, register_admin_and_login, auth_headers, make_session, make_message
import app.services.chat_service as cs
from app.core.exceptions import QuotaExceededError
from app.core.exception_handlers import generic_exception_handler
from app.server import rate_limit_handler
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request


# --------------------------------------------------------------------------- #
# RAG mock(让 /send、/stream 跑通真实 _chat_events 管线,不触发网络)
# --------------------------------------------------------------------------- #
class _FakeResult:
    def __init__(self, content, doc_id, doc_name, chunk_id, score, chunk_index=0):
        self.content = content
        self.doc_id = doc_id
        self.doc_name = doc_name
        self.chunk_id = chunk_id
        self.score = score
        self.chunk_index = chunk_index


class _FakeRetriever:
    def retrieve_with_fallback(self, query, kb_id="default"):
        return [_FakeResult("退货政策:7 天无理由退货。", 1, "退货政策.txt", "doc_1_chunk_0", 0.92)]


class _FakeLLMClient:
    def chat_stream(self, messages, temperature=0.7, max_tokens=1000):
        for chunk in ["您好,", "关于退货"]:
            yield chunk


def _mock_rag(monkeypatch):
    monkeypatch.setattr(cs, "get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr(cs, "get_llm_client", lambda: _FakeLLMClient())


def _patch_quota(monkeypatch, kind="ok"):
    """kind: 'ok' 放行 / 'exceeded' 抛 QuotaExceededError / 'boom' 抛普通异常(测 500)。"""
    if kind == "ok":
        monkeypatch.setattr(cs.ChatService, "check_quota", staticmethod(lambda db, user_id: None))
    elif kind == "exceeded":
        monkeypatch.setattr(
            cs.ChatService, "check_quota",
            staticmethod(lambda db, user_id: (_ for _ in ()).throw(QuotaExceededError("Daily quota exceeded"))),
        )
    elif kind == "boom":
        monkeypatch.setattr(
            cs.ChatService, "check_quota",
            staticmethod(lambda db, user_id: (_ for _ in ()).throw(RuntimeError("db gone"))),
        )


# --------------------------------------------------------------------------- #
# SC03: 会话空标题保留
# --------------------------------------------------------------------------- #
def test_session_empty_title_preserved(client):
    creds = register_and_login(client, email="sc03@example.com")
    h = auth_headers(creds["token"])
    r = client.post("/api/sessions", json={"title": ""}, headers=h)
    assert r.status_code == 200
    # 关键回归:空字符串应原样保留,而不是被默认成"新对话"
    assert r.json()["data"]["title"] == ""


def test_session_default_title_still_works(client):
    creds = register_and_login(client, email="sc03b@example.com")
    h = auth_headers(creds["token"])
    r = client.post("/api/sessions", json={}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新对话"


# --------------------------------------------------------------------------- #
# KL02: 知识库按用户隔离(列表 / 按 id 获取 / 删除)
# --------------------------------------------------------------------------- #
def test_kb_list_isolation_new_account_empty(client):
    # 全新账号(无文档)列表应为空 —— 验证不会泄露其它用户的文档
    creds = register_admin_and_login(client, email="kl02@example.com")
    h = auth_headers(creds["token"])
    r = client.get("/api/kb/documents", headers=h)
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_kb_get_isolation_cross_user(client):
    u1 = register_admin_and_login(client, email="kl02a@example.com")
    u2 = register_admin_and_login(client, email="kl02b@example.com")
    h1, h2 = auth_headers(u1["token"]), auth_headers(u2["token"])
    doc_id = client.post(
        "/api/kb/documents", files={"file": ("doc.txt", b"hi", "text/plain")}, headers=h1
    ).json()["data"]["document_id"]
    # 用户2 不能读取用户1 的文档 -> 404
    r = client.get(f"/api/kb/documents/{doc_id}", headers=h2)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_kb_delete_isolation_cross_user(client):
    u1 = register_admin_and_login(client, email="kl02c@example.com")
    u2 = register_admin_and_login(client, email="kl02d@example.com")
    h1, h2 = auth_headers(u1["token"]), auth_headers(u2["token"])
    doc_id = client.post(
        "/api/kb/documents", files={"file": ("doc.txt", b"hi", "text/plain")}, headers=h1
    ).json()["data"]["document_id"]
    # 用户2 不能删除用户1 的文档 -> 404
    r = client.delete(f"/api/kb/documents/{doc_id}", headers=h2)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"
    # 用户1 自己的删除仍然成功
    assert client.delete(f"/api/kb/documents/{doc_id}", headers=h1).status_code == 200


# --------------------------------------------------------------------------- #
# 聊天会话预校验:引用不存在的 session -> 400(而非流式中途崩溃)
# --------------------------------------------------------------------------- #
def test_chat_send_unknown_session_400(client, monkeypatch):
    creds = register_and_login(client, email="cv1@example.com")
    h = auth_headers(creds["token"])
    _patch_quota(monkeypatch, "ok")
    r = client.post("/api/chat/send", json={"message": "hi", "session_id": 999999}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert "Session not found" in r.json()["detail"]["message"]


def test_chat_stream_unknown_session_400(client, monkeypatch):
    creds = register_and_login(client, email="cv2@example.com")
    h = auth_headers(creds["token"])
    _patch_quota(monkeypatch, "ok")
    r = client.post("/api/chat/stream", json={"message": "hi", "session_id": 999999}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_chat_send_happy_path_format(client, monkeypatch):
    creds = register_and_login(client, email="cv3@example.com")
    h = auth_headers(creds["token"])
    _mock_rag(monkeypatch)
    _patch_quota(monkeypatch, "ok")
    r = client.post("/api/chat/send", json={"message": "怎么退货"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    # 成功响应采用 ApiResponse 信封
    assert body["success"] is True
    assert body["code"] == "SUCCESS"
    data = body["data"]
    assert isinstance(data["session_id"], int)
    assert isinstance(data["message_id"], int)
    assert data["content"]  # 非空
    assert data["finish_reason"] in ("stop", "no_context", "error")
    assert isinstance(data["sources"], list)


def test_chat_stream_sse_structure(client, monkeypatch):
    creds = register_and_login(client, email="cv4@example.com")
    h = auth_headers(creds["token"])
    _mock_rag(monkeypatch)
    _patch_quota(monkeypatch, "ok")
    r = client.post("/api/chat/stream", json={"message": "怎么退货"}, headers=h)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    events = []
    for block in r.text.split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            events.append(json.loads(block[len("data:"):].strip()))
    types = [e["type"] for e in events]
    assert "session_id" in types
    assert "content" in types
    assert "done" in types
    done = next(e for e in events if e["type"] == "done")
    assert isinstance(done["data"]["message_id"], int)


# --------------------------------------------------------------------------- #
# 错误响应格式合规:所有非 422 失败统一为 {"detail": {code, message}}
# --------------------------------------------------------------------------- #
def test_error_format_401(client):
    r = client.get("/api/sessions")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "AUTH_ERROR"
    assert "message" in r.json()["detail"]


def test_error_format_400(client):
    r = client.post("/api/auth/register", json={"password": "password123"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_error_format_404(client):
    creds = register_and_login(client, email="ef1@example.com")
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions/999999", headers=h)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_error_format_422_is_array(client):
    # Pydantic 校验错误:FastAPI 默认包裹为 {"detail": [字段错误列表]}
    # (顶层仍有 detail 键,与 4xx/5xx 的 {detail:{code,message}} 结构保持外框一致)
    r = client.post("/api/auth/register", json={"email": "x", "password": "12345"})
    assert r.status_code == 422
    body = r.json()
    assert isinstance(body, dict)
    assert isinstance(body["detail"], list)
    assert "loc" in body["detail"][0] and "msg" in body["detail"][0] and "type" in body["detail"][0]


def test_error_format_429_quota(client, monkeypatch):
    creds = register_and_login(client, email="ef2@example.com")
    h = auth_headers(creds["token"])
    _patch_quota(monkeypatch, "exceeded")
    r = client.post("/api/chat/send", json={"message": "hi"}, headers=h)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "QUOTA_EXCEEDED"


def test_error_format_500_generic():
    # 非 BaseAppException(数据库故障等)经 generic handler 统一为 500 信封。
    # 单测 handler 本身验证格式;集成层面 get_db 在 anyio TaskGroup 中抛错会被
    # 包成 ExceptionGroup,TestClient 默认会原样重抛,属测试环境特性,生产(uvicorn)
    # 下 handler 已注册(server.py: add_exception_handler(Exception, ...))会正确返回 500。
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    resp = asyncio.run(generic_exception_handler(req, RuntimeError("db gone")))
    assert resp.status_code == 500
    body = json.loads(resp.body)
    assert body["detail"]["code"] == "INTERNAL_ERROR"
    assert "message" in body["detail"]


def test_rate_limit_handler_format():
    # 限流 429 必须采用与其它错误一致的 {detail:{code,message}} 信封
    # RateLimitExceeded 需要传入一个带 error_message 的 limit 对象
    from types import SimpleNamespace
    exc = RateLimitExceeded(SimpleNamespace(error_message="Rate limit exceeded"))
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    resp = asyncio.run(rate_limit_handler(req, exc))
    assert resp.status_code == 429
    body = json.loads(resp.body)
    assert body["detail"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "message" in body["detail"]


# --------------------------------------------------------------------------- #
# 跨用户越权访问返回 404
# --------------------------------------------------------------------------- #
def test_session_cross_user_404(client):
    u1 = register_and_login(client, email="xu1@example.com")
    u2 = register_and_login(client, email="xu2@example.com")
    h1, h2 = auth_headers(u1["token"]), auth_headers(u2["token"])
    sid = client.post("/api/sessions", json={}, headers=h1).json()["data"]["id"]
    r = client.get(f"/api/sessions/{sid}", headers=h2)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_feedback_cross_user_404(client, db):
    u1 = register_and_login(client, email="xf1@example.com")
    u2 = register_and_login(client, email="xf2@example.com")
    h1, h2 = auth_headers(u1["token"]), auth_headers(u2["token"])
    sess = make_session(db, u1["user_id"])
    msg = make_message(db, sess.id)
    fb_id = client.post(
        "/api/feedback", json={"message_id": msg.id, "rating": 1}, headers=h1
    ).json()["data"]["id"]
    # 用户2 不能读取/删除用户1 的反馈
    assert client.get(f"/api/feedback/{fb_id}", headers=h2).status_code == 404
    assert client.delete(f"/api/feedback/{fb_id}", headers=h2).status_code == 404
