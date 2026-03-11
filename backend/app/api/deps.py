"""
FastAPI 依赖注入
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.repositories import DocumentRepository, TaskRepository


# ── 数据库会话 ────────────────────────────────────────────────────────

async def get_task_repo(db: AsyncSession = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)

async def get_doc_repo(db: AsyncSession = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


# ── 当前用户（开发阶段简化版）────────────────────────────────────────

async def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """
    开发阶段：从 Header X-User-Id 获取用户 ID。
    AUTH_DISABLED=true 时返回默认开发用户。
    生产环境：替换为 JWT 解析逻辑。
    """
    if settings.auth_disabled:
        return x_user_id or "00000000-0000-0000-0000-000000000001"

    if not x_user_id:
        raise HTTPException(status_code=401, detail="未提供用户认证信息")

    return x_user_id
