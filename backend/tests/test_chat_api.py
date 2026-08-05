"""
聊天(SSE 流式)接口测试
POST /api/chat/stream
需鉴权;含消息长度校验、配额校验、流式响应结构校验。
注:LLM 流式生成已在用例内 mock,避免触发真实 DashScope 调用。
"""
from tests.helpers import register_and_login, auth_headers
import app.services.chat_service as cs
from app.core.exceptions import QuotaExceededError


def _login(client):
    return register_and_login(client, email="chat@example.com")


def _mock_stream(monkeypatch, chunks, quota_ok=True):
    """mock 掉 chat_stream 与 quota 检查。"""
    async def fake_chat_stream(user_id, request):
        for c in chunks:
            yield c

    monkeypatch.setattr(cs.ChatService, "chat_stream", staticmethod(fake_chat_stream))

    if quota_ok:
        def fake_check_quota(db, user_id):
            return None
    else:
        def fake_check_quota(db, user_id):
            raise QuotaExceededError("Daily quota exceeded")

    monkeypatch.setattr(cs.ChatService, "check_quota", staticmethod(fake_check_quota))


def test_stream_no_auth(client):
    r = client.post("/api/chat/stream", json={"message": "hi"})
    assert r.status_code == 401


def test_stream_success(client, monkeypatch):
    creds = _login(client)
    h = auth_headers(creds["token"])
    _mock_stream(monkeypatch, [
        'data: {"event":"content","data":"你好"}\n\n',
        'data: {"event":"done","data":{"sources":[]}}\n\n',
    ])
    r = client.post("/api/chat/stream", json={"message": "你好"}, headers=h)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "你好" in r.text


def test_stream_empty_message(client, monkeypatch):
    creds = _login(client)
    h = auth_headers(creds["token"])
    _mock_stream(monkeypatch, ["data: {}\n\n"])
    r = client.post("/api/chat/stream", json={"message": ""}, headers=h)
    assert r.status_code == 422  # min_length=1


def test_stream_message_too_long(client, monkeypatch):
    creds = _login(client)
    h = auth_headers(creds["token"])
    _mock_stream(monkeypatch, ["data: {}\n\n"])
    # ChatRequest.message 不设 max_length(见 schema 注释),超长由端点返回
    # 400 INVALID_REQUEST,而非 pydantic 的 422(这样错误消息更明确)。
    long_msg = "x" * 501
    r = client.post("/api/chat/stream", json={"message": long_msg}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_REQUEST"


def test_stream_message_boundary_500(client, monkeypatch):
    creds = _login(client)
    h = auth_headers(creds["token"])
    _mock_stream(monkeypatch, ['data: {"event":"content","data":"ok"}\n\n'])
    # 边界值:恰好 500 字符应成功
    r = client.post("/api/chat/stream", json={"message": "x" * 500}, headers=h)
    assert r.status_code == 200


def test_stream_quota_exceeded(client, monkeypatch):
    creds = _login(client)
    h = auth_headers(creds["token"])
    _mock_stream(monkeypatch, ["data: {}\n\n"], quota_ok=False)
    r = client.post("/api/chat/stream", json={"message": "hi"}, headers=h)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "QUOTA_EXCEEDED"
