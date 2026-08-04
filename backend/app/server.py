"""
FastAPI 应用定义（Application 本体）

本模块定义 FastAPI 实例、路由、中间件与 lifespan。
启动入口在 backend/main.py（执行 `python main.py` 即可启动）。
"""
import os

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import BaseAppException
from app.core.exception_handlers import base_app_exception_handler, generic_exception_handler
from app.core.ratelimit import limiter  # shared slowapi instance
from app.core.tracing import (
    generate_trace_id,
    set_current_trace_id,
    reset_current_trace_id,
)
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting AI Customer Service System")

    # Ensure database tables exist (safe no-op if init_db.sql already ran).
    # 失败直接抛出,让启动期就暴露数据库问题(不可达/库不存在/无建表权限),
    # 而不是让服务"假装启动成功"、之后每个接口都返回 500 INTERNAL_ERROR。
    from app.database import init_db
    try:
        init_db()
    except Exception as e:
        logger.critical("Database initialization failed: %s", e)
        raise

    # 引导创建管理员账号(幂等, 非致命): 已存在则跳过, 未配置则跳过。
    # 保证系统始终至少有一个 admin, 且普通用户无法经公开注册拿到 admin 角色。
    # 测试模式下跳过: TestClient 的 lifespan 会触发本调用, 避免在 _test 库建 admin 污染用例。
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from app.services.admin_bootstrap import ensure_admin
            ensure_admin()
        except Exception as e:  # pragma: no cover - 尽力而为, 不阻断启动
            logger.warning("Admin bootstrap error (non-fatal): %s", e)

    # Optionally seed the knowledge base from seed_docs so the RAG chain is
    # testable right after startup. Controlled by AUTO_INIT_KB (default off) to
    # avoid triggering network embeddings on every boot. Idempotent: already
    # ingested docs are skipped.
    if settings.auto_init_kb:
        logger.info("AUTO_INIT_KB enabled -> seeding knowledge base from seed_docs ...")
        try:
            from fastapi.concurrency import run_in_threadpool
            from app.services.init_service import seed_knowledge_base
            result = await run_in_threadpool(seed_knowledge_base)
            logger.info(
                "Knowledge base seeding done: seeded=%d skipped=%d failed=%d",
                len(result.get("seeded", [])),
                len(result.get("skipped", [])),
                len(result.get("failed", [])),
            )
        except Exception as e:
            logger.error(f"Knowledge base auto-seeding failed: {e}")

    yield
    logger.info("Shutting down AI Customer Service System")


# Create FastAPI application
# 禁用 FastAPI 内置的 /docs、/redoc 路由,改用下方自定义的本地资源版本
# (内置路由会把 Swagger UI 资源硬编码指向外网 CDN,离线/受限网络下页面加载失败)。
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered customer service system with RAG capabilities",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Add rate limiter to app state
app.state.limiter = limiter


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 handler.

    slowapi's default handler returns ``{"error": "..."}`` which is inconsistent
    with the rest of the API (every other 4xx/5xx uses ``{detail:{code,message}}``).
    Override it so rate-limit rejections share the uniform error envelope.
    """
    return JSONResponse(
        status_code=429,
        content={"detail": {"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded. Please slow down and retry later."}},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Trace middleware (raw ASGI class, NOT BaseHTTPMiddleware).
#
# IMPORTANT: Starlette's `@app.middleware("http")` / BaseHTTPMiddleware runs the
# endpoint in a separate task via `ensure_future`, which does NOT propagate
# contextvars set here into the endpoint — so a span created downstream would get
# a different (auto-minted) trace_id than the one echoed on the response. A raw
# ASGI middleware class calls `self.app(...)` in the SAME task, so the
# request-scoped TraceId contextvar propagates correctly to every span.
class TraceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        raw = None
        for k, v in scope.get("headers", []):
            if k.lower() in (b"x-trace-id", b"x-request-id"):
                raw = v
                break
        trace_id = raw.decode("utf-8") if raw else generate_trace_id()
        token = set_current_trace_id(trace_id)
        # Also stash on request.state so a per-request FastAPI dependency can
        # re-assert the contextvar inside the endpoint's own task if needed.
        scope.setdefault("state", {})["trace_id"] = trace_id

        # Echo the TraceId on the response so clients can correlate logs/traces.
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode("utf-8")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            reset_current_trace_id(token)


app.add_middleware(TraceMiddleware)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version
    }


# 本地打包的 Swagger UI / ReDoc(不依赖外网 CDN,离线可用)
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """离线可用的 Swagger UI 页面：复用内置 openapi.json，静态资源指向本地 /static。"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} - Swagger UI",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """离线可用的 ReDoc 页面：复用内置 openapi.json，静态资源指向本地 /static/redoc。"""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} - ReDoc",
        redoc_js_url="/static/redoc/redoc.standalone.js",
    )


# Register exception handlers
app.add_exception_handler(BaseAppException, base_app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include routers. The `trace_context` dependency re-asserts the request TraceId
# contextvar inside each endpoint's task. The raw ASGI TraceMiddleware already sets
# it for the common async case, but a sync endpoint runs in a threadpool where the
# contextvar is lost — this dependency is the defense-in-depth safeguard that keeps
# every span (sync or async) sharing the echoed TraceId.
from app.core.tracing import trace_context

_trace_dep = [Depends(trace_context)]
from app.api import auth, session, knowledge, chat, feedback, trace as trace_router, stats
app.include_router(auth.router, prefix="/api/auth", tags=["auth"], dependencies=_trace_dep)
app.include_router(session.router, prefix="/api/sessions", tags=["sessions"], dependencies=_trace_dep)
app.include_router(knowledge.router, prefix="/api/kb", tags=["knowledge"], dependencies=_trace_dep)
app.include_router(chat.router, prefix="/api/chat", tags=["chat"], dependencies=_trace_dep)
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"], dependencies=_trace_dep)
app.include_router(stats.router, prefix="/api/stats", tags=["admin-stats"], dependencies=_trace_dep)
app.include_router(trace_router.router, tags=["traces"], dependencies=_trace_dep)

# Serve bundled Swagger UI / ReDoc assets locally (offline-friendly)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    log_config = setup_logging()
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=log_config,
    )
