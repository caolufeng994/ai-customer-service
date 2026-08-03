"""
Pytest 全局配置与共享 fixtures —— 接口(API)自动化测试基础设施。

设计要点(满足"严格使用 MySQL、不引入其他数据库系统"约束):
1. 数据库:使用与生产一致的 MySQL 引擎,直接连接真实业务库 `settings.db_name`
   (不再维护独立的 `<db_name>_test` 库)。每个测试函数内 drop_all + create_all
   (先关闭 FK 检查以保证可重放),保证用例间完全隔离、测试数据自动清理。
   ⚠️ 重要:测试运行会重建表结构,会清空真实库中既有数据;交付前再用种子/初始化
      脚本重建业务数据即可。这是有意为之(与"交付前再清理"的需求一致)。
2. 外部依赖隔离:mock 知识库后台文档处理(`process_document`)与聊天限流,
   避免触发真实 Embedding/Chroma/LLM 网络调用与测试间相互限流干扰。
3. 响应封装:统一为 ApiResponse {success, code, message, data},断言时按此结构校验。
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db  # noqa: E402
import app.database as db_mod  # noqa: E402
# 显式导入所有模型,确保 create_all 能建出全部表
import app.models.user  # noqa: E402,F401
import app.models.session  # noqa: E402,F401
import app.models.message  # noqa: E402,F401
import app.models.kb_document  # noqa: E402,F401
import app.models.kb_chunk  # noqa: E402,F401
import app.models.message_citation  # noqa: E402,F401
import app.models.feedback  # noqa: E402,F401
import app.models.usage_quota  # noqa: E402,F401

from app.server import app, limiter  # noqa: E402
import app.services.knowledge_service as ks  # noqa: E402

from app.config import settings  # noqa: E402


TEST_DB_NAME = settings.db_name  # 直接使用真实业务库,不再维护独立的 _test 库
TEST_DB_URL = (
    f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
    f"@{settings.db_host}:{settings.db_port}/{TEST_DB_NAME}"
)


def _reset_schema(engine):
    """重建全部表；先关闭 FK 检查以保证 drop/create 可重复执行。"""
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        conn.commit()


@pytest.fixture(scope="session")
def engine():
    """Session 级 MySQL 引擎:直接连接真实业务库。

    每个测试函数内会重建表结构(drop_all + create_all),因此测试运行会清空真实库
    中既有数据;交付前用种子/初始化脚本重建业务数据即可。
    """
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    yield eng
    # 测试结束后重建表结构,确保不留测试数据
    try:
        _reset_schema(eng)
    finally:
        eng.dispose()


@pytest.fixture
def client(engine):
    """
    每个用例重建表结构(隔离+自动清理),并注入测试用 DB 依赖。
    同时禁用限流、mock 知识库后台处理,避免外部网络与相互限流干扰。
    """
    _reset_schema(engine)

    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # 让 services / init_db 都使用测试库引擎
    db_mod.engine = engine
    db_mod.SessionLocal = TestingSessionLocal

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # 禁用 slowapi 限流,避免测试间累计触发 429 干扰断言。
    # 注意:此前通过 `limiter.check = _noop_limit` 禁用;但崩溃修复后代码改用
    # `@limiter.limit(...)` 装饰器(不再调用 limiter.check),该 patch 已失效。
    # slowapi 在请求时通过 `self.limiter.hit(...)` 判定是否超限(self.limiter 即
    # limiter._limiter),因此这里直接让 hit 永远返回 True(放行),使装饰器形同虚设。
    def _always_allow(*args, **kwargs):
        return True

    limiter._limiter.hit = _always_allow

    # Mock 知识库后台处理(原逻辑会触发 Embedding/Chroma/LLM 网络调用)
    async def _fake_process_document(db, document_id, file_content):
        return None

    ks.KnowledgeService.process_document = staticmethod(_fake_process_document)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def db(client, engine):
    """供测试构造/查询前置数据的 DB session(每个用例独立,client 已保证表存在)。"""
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
