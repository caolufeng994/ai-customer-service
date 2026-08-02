"""
FastAPI 应用定义（Application 本体）

本模块定义 FastAPI 实例、路由、中间件与 lifespan。
启动入口在 backend/main.py（执行 `python main.py` 即可启动）。
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import BaseAppException
from app.core.exception_handlers import base_app_exception_handler, generic_exception_handler
import logging

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Include routers
from app.api import auth, session, knowledge, chat, feedback
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(session.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(knowledge.router, prefix="/api/kb", tags=["knowledge"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])

# Serve bundled Swagger UI / ReDoc assets locally (offline-friendly)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    setup_logging()
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
