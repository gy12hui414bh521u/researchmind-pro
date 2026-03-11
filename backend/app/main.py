"""
ResearchMind Pro — FastAPI 应用入口
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

logger = structlog.get_logger()


# ── Lifespan：应用启动/关闭 ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 启动 ──────────────────────────────────────────────────────────
    from app.utils.logging import setup_logging
    setup_logging()

    from app.utils.tracing import setup_langsmith
    ls_enabled = setup_langsmith()

    logger.info("ResearchMind Pro 启动中...", version=settings.app_version)
    if ls_enabled:
        logger.info("✅ LangSmith 追踪已启用", project=settings.langchain_project)

    # 配置检查
    warnings = settings.validate_startup()
    for w in warnings:
        logger.warning(w)

    # 初始化 LangGraph
    from app.agents.graph import init_graph
    await init_graph()

    logger.info(
        "✅ 启动完成",
        environment=settings.environment.value,
        providers=settings.available_providers,
    )

    yield

    # ── 关闭 ──────────────────────────────────────────────────────────
    logger.info("ResearchMind Pro 正在关闭...")
    from app.db.database import close_db
    await close_db()
    from app.memory.store import get_memory_store
    await get_memory_store().close()
    logger.info("✅ 已关闭")


# ── FastAPI App ───────────────────────────────────────────────────────

app = FastAPI(
    title=       settings.app_name,
    version=     settings.app_version,
    description= settings.app_description,
    docs_url=    "/docs" if not settings.is_production else None,
    redoc_url=   "/redoc" if not settings.is_production else None,
    lifespan=    lifespan,
)


# ── 中间件 ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=     settings.allowed_origins,
    allow_credentials= True,
    allow_methods=     ["*"],
    allow_headers=     ["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = round((time.time() - start) * 1000)
    logger.info("HTTP",
        method=request.method, path=request.url.path,
        status=response.status_code, ms=elapsed,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误",
                 "error": str(exc) if settings.debug else "请联系管理员"},
    )


# ── 路由注册 ──────────────────────────────────────────────────────────

from app.api import health, tasks, knowledge

app.include_router(health.router,    prefix="/api/v1",        tags=["健康检查"])
app.include_router(tasks.router,     prefix="/api/v1/tasks",  tags=["研究任务"])
app.include_router(knowledge.router, prefix="/api/v1/kb",     tags=["知识库"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name":        settings.app_name,
        "version":     settings.app_version,
        "environment": settings.environment.value,
        "docs":        "/docs",
    }
