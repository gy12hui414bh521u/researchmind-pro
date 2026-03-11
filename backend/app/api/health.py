"""
健康检查路由
GET /api/v1/health        — 基础存活检查
GET /api/v1/health/detail — 各组件详细状态
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


@router.get("/health/detail")
async def health_detail():
    """检查所有依赖组件的连通性"""
    results: dict = {}

    # PostgreSQL
    try:
        from app.db.database import check_db_connection
        results["postgres"] = "ok" if await check_db_connection() else "error"
    except Exception as e:
        results["postgres"] = f"error: {e}"

    # Qdrant
    try:
        from app.rag.retriever import get_collection_stats
        stats = await get_collection_stats()
        results["qdrant"] = "ok" if stats["status"] != "unavailable" else "error"
        results["qdrant_vectors"] = stats.get("vectors_count", 0)
    except Exception as e:
        results["qdrant"] = f"error: {e}"

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        results["redis"] = "ok"
    except Exception as e:
        results["redis"] = f"error: {e}"

    # LLM Providers
    results["llm_providers"] = settings.available_providers
    results["embedding"]     = settings.embedding_provider

    overall = "ok" if all(v == "ok" for k, v in results.items()
                          if k in ("postgres", "qdrant", "redis")) else "degraded"

    return {"status": overall, "components": results}
