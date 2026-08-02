"""
会话接口测试
GET    /api/sessions
POST   /api/sessions
GET    /api/sessions/{id}
PUT    /api/sessions/{id}        (query: title)
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
    r = client.put(f"/api/sessions/{created['id']}", params={"title": "新标题"}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新标题"


def test_update_session_missing_title(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    created = client.post("/api/sessions", json={}, headers=h).json()["data"]
    r = client.put(f"/api/sessions/{created['id']}", headers=h)  # 缺 title 必填
    assert r.status_code == 422


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
