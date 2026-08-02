"""
认证接口测试
POST /api/auth/register
POST /api/auth/login
覆盖正常场景 + 异常场景(缺参/类型错/重复/边界值)。
"""
from tests.helpers import register_user, login_user, register_and_login


def test_register_success(client):
    r = register_user(client, email="alice@example.com")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["code"] == "SUCCESS"
    data = body["data"]
    assert isinstance(data["id"], int)
    assert data["email"] == "alice@example.com"
    # 安全:响应中绝不可泄露密码哈希或盐
    assert "password_hash" not in data
    assert "salt" not in data


def test_register_missing_password(client):
    r = client.post("/api/auth/register", json={"email": "bob@example.com"})
    assert r.status_code == 422  # pydantic 必填校验


def test_register_missing_phone_and_email(client):
    # 既无 phone 也无 email -> 业务校验失败
    r = client.post("/api/auth/register", json={"password": "password123"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_register_invalid_email(client):
    r = register_user(client, email="not-an-email")
    assert r.status_code == 422  # EmailStr 格式校验


def test_register_short_password(client):
    # 等价类:低于 min_length(6)
    r = register_user(client, email="short@example.com", password="12345")
    assert r.status_code == 422


def test_register_password_boundary(client):
    # 边界值:恰好等于 min_length(6) 应成功
    r = register_user(client, email="boundary@example.com", password="123456")
    assert r.status_code == 200


def test_register_duplicate_email(client):
    register_user(client, email="dup@example.com")
    r2 = register_user(client, email="dup@example.com")
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert "already" in r2.json()["detail"]["message"].lower()


def test_register_phone_only_and_login_by_phone(client):
    r = register_user(client, phone="13800000000")
    assert r.status_code == 200
    assert r.json()["data"]["phone"] == "13800000000"
    login = login_user(client, "13800000000")
    assert login.status_code == 200
    assert "token" in login.json()["data"]


def test_login_success(client):
    # register_and_login 内部已断言 200
    creds = register_and_login(client, email="loginok@example.com")
    assert "token" in creds and isinstance(creds["user_id"], int)


def test_login_wrong_password(client):
    register_user(client, email="wrongpw@example.com")
    r = login_user(client, "wrongpw@example.com", password="wrongpass")
    assert r.status_code == 401


def test_login_nonexistent_user(client):
    r = login_user(client, "nobody@example.com")
    assert r.status_code == 401


def test_login_missing_fields(client):
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 422
