"""
管理后台反馈管理接口测试

覆盖：
- 管理员可查看全量反馈，且明细带富化上下文(用户账号/会话标题/关联消息正文)
- 按 rating / reason 过滤
- 汇总接口(总数/点赞/点踩/按原因分布)
- 非管理员访问返回 403
"""
import app.database as db_mod
from tests.helpers import (
    register_and_login,
    register_admin_and_login,
    auth_headers,
    make_session,
    make_message,
)


def _seed_feedbacks(client, token, user_id):
    """在测试库建会话+两条消息,经 API 分别提交一条点赞与一条带原因的点踩反馈。

    注意:feedbacks 表对 (message_id, user_id) 有唯一约束,同一用户对同一条消息
    只能反馈一次,因此点赞/点踩必须落在不同消息上。
    """
    db = db_mod.SessionLocal()
    try:
        sess = make_session(db, user_id, title="测试会话A")
        msg_like = make_message(db, sess.id, content="这是一条正确的回答", role="assistant")
        msg_bad = make_message(db, sess.id, content="这是被评价的错误回答内容", role="assistant")
        # 会话关闭前取出 id,避免实例 detached 后访问 .id 触发惰性加载失败
        like_id = msg_like.id
        bad_id = msg_bad.id
    finally:
        db.close()

    r1 = client.post(
        "/api/feedback",
        json={"message_id": like_id, "rating": 1},
        headers=auth_headers(token),
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/feedback",
        json={
            "message_id": bad_id,
            "rating": -1,
            "reason": "事实错误",
            "comment": "这个答案不对",
        },
        headers=auth_headers(token),
    )
    assert r2.status_code == 200, r2.text


def test_admin_list_feedbacks_enriched(client):
    u = register_and_login(client, email="fbuser@example.com")
    _seed_feedbacks(client, u["token"], u["user_id"])
    admin = register_admin_and_login(client, email="fbadmin@example.com")

    res = client.get("/api/admin/feedbacks", headers=auth_headers(admin["token"]))
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["meta"]["total"] >= 2

    data = body["data"]
    dislikes = [d for d in data if d["rating"] == -1]
    assert len(dislikes) == 1
    d = dislikes[0]
    assert d["reason"] == "事实错误"
    assert d["comment"] == "这个答案不对"
    assert d["user_account"] == "fbuser@example.com"
    assert d["session_title"] == "测试会话A"
    assert "这是被评价的错误回答内容" in (d["message_content"] or "")


def test_admin_filter_by_rating(client):
    u = register_and_login(client, email="fbu2@example.com")
    _seed_feedbacks(client, u["token"], u["user_id"])
    admin = register_admin_and_login(client, email="fbadm2@example.com")

    res = client.get(
        "/api/admin/feedbacks",
        params={"rating": -1},
        headers=auth_headers(admin["token"]),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) >= 1
    assert all(d["rating"] == -1 for d in data)


def test_admin_filter_by_reason(client):
    u = register_and_login(client, email="fbu3@example.com")
    _seed_feedbacks(client, u["token"], u["user_id"])
    admin = register_admin_and_login(client, email="fbadm3@example.com")

    res = client.get(
        "/api/admin/feedbacks",
        params={"reason": "事实错误"},
        headers=auth_headers(admin["token"]),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) >= 1
    assert all(d["reason"] == "事实错误" for d in data)


def test_admin_filter_by_keyword(client):
    u = register_and_login(client, email="fbu6@example.com")
    _seed_feedbacks(client, u["token"], u["user_id"])
    admin = register_admin_and_login(client, email="fbadm6@example.com")

    res = client.get(
        "/api/admin/feedbacks",
        params={"keyword": "这个答案不对"},
        headers=auth_headers(admin["token"]),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) >= 1
    assert all("这个答案不对" in (d["comment"] or "") for d in data)


def test_admin_summary(client):
    u = register_and_login(client, email="fbu4@example.com")
    _seed_feedbacks(client, u["token"], u["user_id"])
    admin = register_admin_and_login(client, email="fbadm4@example.com")

    res = client.get(
        "/api/admin/feedbacks/summary", headers=auth_headers(admin["token"])
    )
    assert res.status_code == 200
    s = res.json()["data"]
    assert s["total"] >= 2
    assert s["dislike_count"] >= 1
    assert s["like_count"] >= 1
    assert s["by_reason"].get("事实错误", 0) >= 1


def test_non_admin_forbidden(client):
    u = register_and_login(client, email="fbu5@example.com")
    res = client.get("/api/admin/feedbacks", headers=auth_headers(u["token"]))
    assert res.status_code == 403
