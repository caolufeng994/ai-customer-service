"""
接口测试辅助函数(非测试模块,不会被 pytest 收集)。
用于快速构造已注册用户、获取鉴权头、构造前置数据。
"""
from app.models.session import Session as SessionModel
from app.models.message import Message


def register_user(client, email=None, phone=None, password="password123"):
    """注册一个用户,返回原始响应对象。"""
    payload = {"password": password}
    if email is not None:
        payload["email"] = email
    if phone is not None:
        payload["phone"] = phone
    return client.post("/api/auth/register", json=payload)


def login_user(client, identifier, password="password123"):
    """用账号(邮箱或手机号)登录,返回原始响应对象。"""
    return client.post(
        "/api/auth/login",
        json={"phone_or_email": identifier, "password": password},
    )


def register_and_login(client, email="user@example.com", password="password123"):
    """
    注册并登录,返回 {"token", "user_id"} 字典。
    断言注册/登录成功,失败会抛出 AssertionError。
    """
    reg = register_user(client, email=email, password=password)
    assert reg.status_code == 200, f"注册失败: {reg.text}"
    login = login_user(client, email, password)
    assert login.status_code == 200, f"登录失败: {login.text}"
    data = login.json()["data"]
    return {"token": data["token"], "user_id": data["user"]["id"]}


def register_admin_and_login(client, email="admin@example.com", password="password123"):
    """
    注册一个用户并提升为 admin 角色后登录,返回 {"token", "user_id"}。
    用于需要管理员权限的接口测试(知识库管理/统计页)。
    依赖 conftest 的 client fixture 已把 app.database.SessionLocal 指向测试库。
    """
    reg = register_user(client, email=email, password=password)
    assert reg.status_code == 200, f"注册失败: {reg.text}"
    # 提升为 admin
    import app.database as db_mod
    from app.models.user import User
    s = db_mod.SessionLocal()
    try:
        user = s.query(User).filter(User.email == email).first()
        assert user is not None, "注册后未查到用户"
        user.role = "admin"
        s.commit()
    finally:
        s.close()
    # 重新登录,使 JWT 携带 role=admin
    login = login_user(client, email, password)
    assert login.status_code == 200, f"登录失败: {login.text}"
    data = login.json()["data"]
    return {"token": data["token"], "user_id": data["user"]["id"]}


def auth_headers(token):
    """根据 token 生成 Authorization 请求头。"""
    return {"Authorization": f"Bearer {token}"}


def make_session(db, user_id, title="测试会话"):
    """在 DB 中直接创建一条会话,返回 ORM 对象。"""
    sess = SessionModel(user_id=user_id, title=title)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def make_message(db, session_id, content="这是一条测试消息", role="assistant"):
    """在 DB 中直接创建一条消息,返回 ORM 对象。"""
    msg = Message(session_id=session_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
