"""
会话接口测试
GET    /api/sessions
POST   /api/sessions
GET    /api/sessions/{id}
PUT    /api/sessions/{id}        (body: {title})
DELETE /api/sessions/{id}
覆盖鉴权、CRUD、资源不存在、分页边界值。
"""
from tests.helpers import register_and_login, auth_headers


def _login(client):
    return register_and_login(client, email="sess@example.com")


def test_get_sessions_no_auth(client):
    r = client.get("/api/sessions")
    assert r.status_code == 401


def test_get_sessions_empty(client):
    creds = _login(client)
    r = client.get("/api/sessions", headers=auth_headers(creds["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []
    assert body["meta"]["total"] == 0
    assert body["meta"]["page_size"] == 20


def test_create_session_default_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/sessions", json={}, headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["user_id"] == creds["user_id"]
    assert data["title"] == "新对话"
    assert data["msg_count"] == 0


def test_create_session_custom_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/sessions", json={"title": "我的会话"}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "我的会话"


def test_create_session_long_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/sessions", json={"title": "x" * 256}, headers=h)
    assert r.status_code == 422  # max_length=255


def test_get_session_detail(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    r = client.get(f"/api/sessions/{created['id']}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["session"]["id"] == created["id"]
    assert body["data"]["messages"] == []


def test_get_session_not_found(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions/999999", headers=h)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_update_session_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    # title 现在通过 JSON body 传入(不再是 query 参数)
    r = client.put(f"/api/sessions/{created['id']}", json={"title": "新标题"}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新标题"


def test_update_session_empty_title_allowed(client):
    # 与创建接口一致,允许空串清空标题(SC03:保留显式空串)
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={"title": "原标题"}, headers=h).json()["data"]
    r = client.put(f"/api/sessions/{created['id']}", json={"title": ""}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == ""


def test_update_session_missing_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    r = client.put(f"/api/sessions/{created['id']}", headers=h)  # 缺 body/title 必填
    assert r.status_code == 422


def test_update_session_long_title(client):
    # 与创建接口一致,title 受 max_length=255 约束
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    r = client.put(f"/api/sessions/{created['id']}", json={"title": "x" * 256}, headers=h)
    assert r.status_code == 422


def test_detail_msg_count_uses_message_length(client):
    """详情接口 msg_count 必须直接由 len(messages) 派生,
    而非读取可能失同步的冗余计数器(session.msg_count)。"""
    from app.database import SessionLocal
    from app.models.message import Message

    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    sid = created["id"]

    # 直接插入一条消息,但不调用 increment_message_count -> DB 中 msg_count 仍为 0
    with SessionLocal() as db:
        db.add(Message(
            session_id=sid, role="user", content="hi",
            token_in=0, token_out=0, latency_ms=0,
        ))
        db.commit()

    # 此时 DB session.msg_count=0,但 messages 实际有 1 条
    r = client.get(f"/api/sessions/{sid}", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert len(body["messages"]) == 1
    # 关键断言:详情应返回 len(messages)=1,而非失同步的 DB msg_count=0
    assert body["session"]["msg_count"] == 1


def test_delete_session(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    r = client.delete(f"/api/sessions/{created['id']}", headers=h)
    assert r.status_code == 200
    r2 = client.get(f"/api/sessions/{created['id']}", headers=h)
    assert r2.status_code == 404


def test_delete_session_not_found(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.delete("/api/sessions/999999", headers=h)
    assert r.status_code == 404


# ===== 分页边界值 / 等价类 (skip>=0, limit 1..100) =====
def test_pagination_skip_negative(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions", params={"skip": -1}, headers=h)
    assert r.status_code == 422


def test_pagination_limit_zero(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions", params={"limit": 0}, headers=h)
    assert r.status_code == 422


def test_pagination_limit_over_max(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions", params={"limit": 101}, headers=h)
    assert r.status_code == 422


def test_pagination_limit_boundary(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.get("/api/sessions", params={"limit": 100}, headers=h)
    assert r.status_code == 200
    assert r.json()["meta"]["page_size"] == 100
