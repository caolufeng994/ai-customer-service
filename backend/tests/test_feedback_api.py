"""
反馈接口测试
POST /api/feedback
需鉴权;message_id 必须指向存在的消息;rating 范围 [-1, 1]。
"""
from tests.helpers import register_and_login, auth_headers, make_session, make_message


def _setup(client):
    return register_and_login(client, email="fb@example.com")


def test_submit_feedback_no_auth(client):
    r = client.post("/api/feedback", json={"message_id": 1, "rating": 1})
    assert r.status_code == 401


def test_submit_feedback_success(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    sess = make_session(db, creds["user_id"])
    msg = make_message(db, sess.id)
    r = client.post(
        "/api/feedback",
        json={"message_id": msg.id, "rating": 1, "comment": "good"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["message_id"] == msg.id
    assert body["data"]["rating"] == 1
    assert body["data"]["user_id"] == creds["user_id"]


def test_feedback_missing_message_id(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/feedback", json={"rating": 1}, headers=h)
    assert r.status_code == 422  # message_id 必填


def test_feedback_message_id_zero(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    # 等价类:等于边界下限 -1 的非法侧
    r = client.post("/api/feedback", json={"message_id": 0, "rating": 1}, headers=h)
    assert r.status_code == 422  # gt=0


def test_feedback_invalid_rating_low(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/feedback", json={"message_id": 1, "rating": -2}, headers=h)
    assert r.status_code == 422  # ge=-1


def test_feedback_invalid_rating_high(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/feedback", json={"message_id": 1, "rating": 2}, headers=h)
    assert r.status_code == 422  # le=1


def test_feedback_rating_boundary(client, db):
    # 参数化覆盖边界值 -1 / 0 / 1(每条反馈使用独立 message,避免触发重复反馈校验)
    creds = _setup(client)
    h = auth_headers(creds["token"])
    sess = make_session(db, creds["user_id"])
    for rating in (-1, 0, 1):
        msg = make_message(db, sess.id)
        r = client.post(
            "/api/feedback", json={"message_id": msg.id, "rating": rating}, headers=h
        )
        assert r.status_code == 200, f"rating={rating} 应成功"
        assert r.json()["data"]["rating"] == rating


def test_feedback_message_not_found(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    r = client.post("/api/feedback", json={"message_id": 999999, "rating": 1}, headers=h)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_feedback_duplicate(client, db):
    creds = _setup(client)
    h = auth_headers(creds["token"])
    sess = make_session(db, creds["user_id"])
    msg = make_message(db, sess.id)
    payload = {"message_id": msg.id, "rating": 1}
    r1 = client.post("/api/feedback", json=payload, headers=h)
    assert r1.status_code == 200
    r2 = client.post("/api/feedback", json=payload, headers=h)
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "VALIDATION_ERROR"
