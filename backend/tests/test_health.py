"""
健康检查接口测试
GET /health (无需鉴权)
"""


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert isinstance(body.get("app_name"), str)
    assert isinstance(body.get("version"), str)
