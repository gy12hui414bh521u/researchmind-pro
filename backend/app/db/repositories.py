"""
数据库 CRUD 操作层（Repository Pattern）
所有数据库操作都在这里，Agent 和 API 层通过 repository 访问数据库
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import (
    DocumentSourceType,
)
from app.models.task import (
    CostInfo,
    TaskCreate,
    TaskPlan,
    TaskResult,
    TaskStatus,
)

# ══════════════════════════════════════════════════════════════════════
# Task Repository
# ══════════════════════════════════════════════════════════════════════


class TaskRepository:
    """任务 CRUD，使用原生 SQL（避免 ORM 的 lazy load 问题）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, task_in: TaskCreate) -> dict:
        """创建新任务，返回任务 dict"""
        row = await self.db.execute(
            text("""
                INSERT INTO tasks (user_id, query, depth, context, status)
                VALUES (:user_id, :query, :depth, :context, 'pending')
                RETURNING *
            """),
            {
                "user_id": user_id,
                "query": task_in.query,
                "depth": task_in.depth.value,
                "context": json.dumps(task_in.context, ensure_ascii=False),
            },
        )
        return dict(row.mappings().one())

    async def get(self, task_id: str) -> dict | None:
        """按 ID 查询任务"""
        row = await self.db.execute(text("SELECT * FROM tasks WHERE id = :id"), {"id": task_id})
        result = row.mappings().first()
        return dict(result) if result else None

    async def list_by_user(
        self, user_id: str, page: int = 1, size: int = 20
    ) -> tuple[list[dict], int]:
        """分页查询用户的任务列表"""
        offset = (page - 1) * size

        rows = await self.db.execute(
            text("""
                SELECT * FROM tasks
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :size OFFSET :offset
            """),
            {"user_id": user_id, "size": size, "offset": offset},
        )
        items = [dict(r) for r in rows.mappings()]

        count_row = await self.db.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :user_id"), {"user_id": user_id}
        )
        total = count_row.scalar_one()
        return items, total

    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """更新任务状态"""
        extra: dict[str, Any] = {}
        if status == TaskStatus.RESEARCHING:
            extra["started_at"] = datetime.now(UTC)
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            extra["completed_at"] = datetime.now(UTC)

        set_clause = "status = :status"
        params: dict[str, Any] = {"id": task_id, "status": status.value}

        if "started_at" in extra:
            set_clause += ", started_at = :started_at"
            params["started_at"] = extra["started_at"]
        if "completed_at" in extra:
            set_clause += ", completed_at = :completed_at"
            params["completed_at"] = extra["completed_at"]

        await self.db.execute(text(f"UPDATE tasks SET {set_clause} WHERE id = :id"), params)

    async def update_plan(self, task_id: str, plan: TaskPlan) -> None:
        """保存 Planner 输出"""
        await self.db.execute(
            text("""
                UPDATE tasks
                SET plan = :plan, status = 'planning'
                WHERE id = :id
            """),
            {"id": task_id, "plan": json.dumps(plan.model_dump(), ensure_ascii=False)},
        )

    async def update_hitl(self, task_id: str, required: bool, approved: bool | None = None) -> None:
        """更新 HiTL 状态"""
        if approved is None:
            await self.db.execute(
                text("UPDATE tasks SET hitl_required = :req WHERE id = :id"),
                {"id": task_id, "req": required},
            )
        else:
            await self.db.execute(
                text("""
                    UPDATE tasks
                    SET hitl_required = :req, hitl_approved = :approved
                    WHERE id = :id
                """),
                {"id": task_id, "req": required, "approved": approved},
            )

    async def update_result(
        self,
        task_id: str,
        result: TaskResult,
        cost: CostInfo,
        quality_score: float,
        iteration_count: int,
    ) -> None:
        """保存最终结果"""
        await self.db.execute(
            text("""
                UPDATE tasks
                SET result         = :result,
                    quality_score  = :quality_score,
                    iteration_count = :iteration_count,
                    token_input    = :token_input,
                    token_output   = :token_output,
                    cost_usd       = :cost_usd,
                    status         = 'completed',
                    completed_at   = NOW()
                WHERE id = :id
            """),
            {
                "id": task_id,
                "result": json.dumps(result.model_dump(), ensure_ascii=False),
                "quality_score": quality_score,
                "iteration_count": iteration_count,
                "token_input": cost.token_input,
                "token_output": cost.token_output,
                "cost_usd": cost.cost_usd,
            },
        )

    async def update_error(self, task_id: str, error_code: str, message: str) -> None:
        """记录错误信息"""
        await self.db.execute(
            text("""
                UPDATE tasks
                SET status = 'failed',
                    error_code = :code,
                    error_message = :msg,
                    completed_at = NOW()
                WHERE id = :id
            """),
            {"id": task_id, "code": error_code, "msg": message},
        )

    async def cancel(self, task_id: str) -> bool:
        """取消任务（仅 pending/planning 状态可取消）"""
        result = await self.db.execute(
            text("""
                UPDATE tasks
                SET status = 'cancelled', completed_at = NOW()
                WHERE id = :id
                  AND status IN ('pending', 'planning')
                RETURNING id
            """),
            {"id": task_id},
        )
        return result.first() is not None


# ══════════════════════════════════════════════════════════════════════
# Document Repository
# ══════════════════════════════════════════════════════════════════════


class DocumentRepository:
    """知识库文档 CRUD"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def compute_hash(content: str) -> str:
        """计算内容 SHA256，用于幂等摄取"""
        return hashlib.sha256(content.encode()).hexdigest()

    async def find_by_hash(self, doc_hash: str) -> dict | None:
        """通过内容 hash 查找已存在文档（幂等检查）"""
        row = await self.db.execute(
            text("SELECT * FROM documents WHERE doc_hash = :hash"), {"hash": doc_hash}
        )
        result = row.mappings().first()
        return dict(result) if result else None

    async def create(
        self,
        doc_hash: str,
        title: str | None,
        source_type: DocumentSourceType,
        source_url: str | None,
        file_name: str | None,
        embedding_model: str,
        metadata: dict | None = None,
    ) -> dict:
        """创建文档记录（摄取开始时调用）"""
        row = await self.db.execute(
            text("""
                INSERT INTO documents
                    (doc_hash, title, source_type, source_url, file_name,
                     embedding_model, status, metadata)
                VALUES
                    (:hash, :title, :source_type, :source_url, :file_name,
                     :embedding_model, 'processing', :metadata)
                RETURNING *
            """),
            {
                "hash": doc_hash,
                "title": title,
                "source_type": source_type.value,
                "source_url": source_url,
                "file_name": file_name,
                "embedding_model": embedding_model,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            },
        )
        return dict(row.mappings().one())

    async def update_completed(self, doc_id: str, chunk_count: int) -> None:
        """摄取完成，更新状态"""
        await self.db.execute(
            text("""
                UPDATE documents
                SET status = 'completed', chunk_count = :count, updated_at = NOW()
                WHERE id = :id
            """),
            {"id": doc_id, "count": chunk_count},
        )

    async def update_failed(self, doc_id: str, error: str) -> None:
        """摄取失败"""
        await self.db.execute(
            text("""
                UPDATE documents
                SET status = 'failed', error_message = :error, updated_at = NOW()
                WHERE id = :id
            """),
            {"id": doc_id, "error": error},
        )

    async def get(self, doc_id: str) -> dict | None:
        row = await self.db.execute(text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id})
        result = row.mappings().first()
        return dict(result) if result else None

    async def list_all(
        self, page: int = 1, size: int = 20, status: str | None = None
    ) -> tuple[list[dict], int]:
        """分页查询文档列表"""
        offset = (page - 1) * size
        where = "WHERE status = :status" if status else ""
        params: dict[str, Any] = {"size": size, "offset": offset}
        if status:
            params["status"] = status

        rows = await self.db.execute(
            text(f"""
                SELECT * FROM documents {where}
                ORDER BY created_at DESC
                LIMIT :size OFFSET :offset
            """),
            params,
        )
        items = [dict(r) for r in rows.mappings()]

        count_row = await self.db.execute(
            text(f"SELECT COUNT(*) FROM documents {where}"), {"status": status} if status else {}
        )
        total = count_row.scalar_one()
        return items, total

    async def delete(self, doc_id: str) -> bool:
        """删除文档记录（向量数据需另行从 Qdrant 删除）"""
        result = await self.db.execute(
            text("DELETE FROM documents WHERE id = :id RETURNING id"), {"id": doc_id}
        )
        return result.first() is not None

    async def upsert_source(
        self,
        task_id: str,
        doc_id: str | None,
        source_url: str | None,
        source_type: str,
        relevance: float,
        snippet: str,
    ) -> None:
        """记录任务来源（用于报告引用）"""
        await self.db.execute(
            text("""
                INSERT INTO task_sources
                    (task_id, doc_id, source_url, source_type, relevance, snippet)
                VALUES (:task_id, :doc_id, :source_url, :source_type, :relevance, :snippet)
                ON CONFLICT DO NOTHING
            """),
            {
                "task_id": task_id,
                "doc_id": doc_id,
                "source_url": source_url,
                "source_type": source_type,
                "relevance": relevance,
                "snippet": snippet[:500],
            },
        )
