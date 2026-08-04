"""
智能会话标题生成测试
POST /api/sessions/{id}/title
覆盖: LLM 生成并写回 / LLM 失败回退启发式 / 无消息不调用 LLM / 输出清洗(去引号)
"""
from unittest.mock import patch, MagicMock
from tests.helpers import register_and_login, auth_headers
from app.models.message import Message


def _login(client, email="title_t1@example.com"):
    return register_and_login(client, email=email)


def _seed_messages(sid, user_text, asst_text):
    # 必须在函数内导入, 以拿到 conftest 替换为测试库的 SessionLocal 绑定
    from app.database import SessionLocal
    with SessionLocal() as db:
        db.add(Message(session_id=sid, role="user", content=user_text,
                       token_in=0, token_out=0, latency_ms=0))
        db.add(Message(session_id=sid, role="assistant", content=asst_text,
                       token_in=0, token_out=0, latency_ms=0))
        db.commit()


def test_generate_title_uses_llm_and_updates(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    sid = client.post("/api/sessions", json={}, headers=h).json()["data"]["id"]
    _seed_messages(sid, "我的订单什么时候能发货？催促一下", "订单通常在 24 小时内发货...")

    fake_llm = MagicMock()
    fake_llm.chat.return_value = "订单发货时间查询"

    with patch("app.rag.llm_client.LLMClient", return_value=fake_llm):
        r = client.post(f"/api/sessions/{sid}/title", headers=h)

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "订单发货时间查询"
    # 落库校验: 后续详情读取仍是该标题
    again = client.get(f"/api/sessions/{sid}", headers=h).json()["data"]["session"]["title"]
    assert again == "订单发货时间查询"


def test_generate_title_fallback_when_llm_fails(client):
    creds = _login(client, email="title_t2@example.com")
    h = auth_headers(creds["token"])
    sid = client.post("/api/sessions", json={}, headers=h).json()["data"]["id"]
    long_q = "如何申请退款并且退回已经支付的会员费用，需要多久才能到账？"
    _seed_messages(sid, long_q, "请按以下步骤操作...")

    with patch("app.rag.llm_client.LLMClient", side_effect=RuntimeError("no api key")):
        r = client.post(f"/api/sessions/{sid}/title", headers=h)

    assert r.status_code == 200
    # LLM 不可用 -> 回退到首条用户消息前 20 字(与系统自动起标题机制一致)
    assert r.json()["data"]["title"] == long_q[:20] + "…"


def test_generate_title_no_messages_keeps_default(client):
    creds = _login(client, email="title_t3@example.com")
    h = auth_headers(creds["token"])
    sid = client.post("/api/sessions", json={}, headers=h).json()["data"]["id"]

    with patch("app.rag.llm_client.LLMClient") as m:
        r = client.post(f"/api/sessions/{sid}/title", headers=h)

    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新对话"
    m.assert_not_called()  # 无用户消息不应触发 LLM 调用


def test_generate_title_cleans_quotes(client):
    creds = _login(client, email="title_t4@example.com")
    h = auth_headers(creds["token"])
    sid = client.post("/api/sessions", json={}, headers=h).json()["data"]["id"]
    _seed_messages(sid, "发票怎么开？", "进入个人中心...")

    fake_llm = MagicMock()
    fake_llm.chat.return_value = '“发票开具方法”'  # 模型常带引号,需清洗

    with patch("app.rag.llm_client.LLMClient", return_value=fake_llm):
        r = client.post(f"/api/sessions/{sid}/title", headers=h)

    assert r.json()["data"]["title"] == "发票开具方法"
