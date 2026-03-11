"""
研究任务路由

POST   /api/v1/tasks                  — 创建任务（同步返回 task_id）
GET    /api/v1/tasks                  — 任务列表
GET    /api/v1/tasks/{id}             — 任务详情
GET    /api/v1/tasks/{id}/stream      — SSE 流式进度
POST   /api/v1/tasks/{id}/approve     — HiTL 审批
DELETE /api/v1/tasks/{id}             — 取消任务
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_id, get_task_repo
from app.db.repositories import TaskRepository
from app.models.task import (
    TaskApprove,
    TaskCreate,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskStatus,
)

router = APIRouter()


# ── POST /  创建任务 ──────────────────────────────────────────────────


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    task_in: TaskCreate,
    bg: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    task_repo: TaskRepository = Depends(get_task_repo),
):
    """
    创建研究任务并立即返回 task_id。
    实际执行通过 GET /tasks/{id}/stream 的 SSE 连接驱动。
    """
    row = await task_repo.create(user_id, task_in)
    return TaskResponse(
        id=row["id"],
        status=TaskStatus(row["status"]),
        query=row["query"],
        depth=row["depth"],
        created_at=row["created_at"],
    )


# ── GET /  任务列表 ───────────────────────────────────────────────────


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = 1,
    size: int = 20,
    user_id: str = Depends(get_current_user_id),
    task_repo: TaskRepository = Depends(get_task_repo),
):
    items, total = await task_repo.list_by_user(user_id, page, size)
    return TaskListResponse(
        items=[
            TaskResponse(
                id=r["id"],
                status=TaskStatus(r["status"]),
                query=r["query"],
                depth=r["depth"],
                created_at=r["created_at"],
                started_at=r.get("started_at"),
                completed_at=r.get("completed_at"),
            )
            for r in items
        ],
        total=total,
        page=page,
        size=size,
    )


# ── GET /{id}  任务详情 ───────────────────────────────────────────────


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: UUID,
    task_repo: TaskRepository = Depends(get_task_repo),
):
    row = await task_repo.get(str(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    import json

    from app.models.task import CostInfo, TaskPlan, TaskResult

    plan = TaskPlan(**json.loads(row["plan"])) if row.get("plan") else None
    result = TaskResult(**json.loads(row["result"])) if row.get("result") else None

    return TaskDetailResponse(
        id=row["id"],
        status=TaskStatus(row["status"]),
        query=row["query"],
        depth=row["depth"],
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        plan=plan,
        result=result,
        quality_score=row.get("quality_score"),
        iteration_count=row.get("iteration_count", 0),
        hitl_required=row.get("hitl_required", False),
        cost=CostInfo(
            token_input=row.get("token_input", 0),
            token_output=row.get("token_output", 0),
            cost_usd=float(row.get("cost_usd", 0)),
        ),
        error_message=row.get("error_message"),
    )


# ── GET /{id}/stream  SSE 流式进度 ───────────────────────────────────


@router.get("/{task_id}/stream")
async def stream_task(
    task_id: UUID,
    user_id: str = Depends(get_current_user_id),
    task_repo: TaskRepository = Depends(get_task_repo),
):
    """
    SSE 端点：连接后立即启动 Agent 工作流，实时推送进度事件。
    前端使用 EventSource 或 fetch + ReadableStream 接收。
    """
    row = await task_repo.get(str(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    from app.agents.runner import run_research_stream

    async def event_generator():
        # 更新任务状态为 planning
        await task_repo.update_status(task_id=str(task_id), status=TaskStatus.RESEARCHING)

        try:
            async for sse_chunk in run_research_stream(
                task_id=str(task_id),
                user_id=user_id,
                query=row["query"],
                depth=row["depth"],
            ):
                yield sse_chunk

            # 流结束后同步最终状态到 DB
            await _sync_final_state(str(task_id), task_repo)

        except asyncio.CancelledError:
            # 客户端断开连接
            pass
        except Exception as e:
            import json

            yield f"event: task_failed\ndata: {json.dumps({'error': str(e)})}\n\n"
            await task_repo.update_error(str(task_id), "STREAM_ERROR", str(e))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── POST /{id}/approve  HiTL 审批 ────────────────────────────────────


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: UUID,
    approve_in: TaskApprove,
    user_id: str = Depends(get_current_user_id),
    task_repo: TaskRepository = Depends(get_task_repo),
):
    """
    用户对研究计划进行审批（approve / modify / reject）。
    审批后 Graph 从 HiTL 断点恢复继续执行。
    """
    row = await task_repo.get(str(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not row.get("hitl_required"):
        raise HTTPException(status_code=400, detail="该任务当前不需要审批")

    approved = approve_in.action == "approve"
    await task_repo.update_hitl(str(task_id), required=False, approved=approved)

    if approve_in.action == "reject":
        await task_repo.cancel(str(task_id))
        return {"status": "cancelled", "message": "任务已取消"}

    # 通知 Graph 恢复执行（通过 Redis pub/sub 或直接 resume）
    await _trigger_resume(str(task_id), approve_in)

    return {"status": "resumed", "message": "审批完成，任务继续执行"}


# ── DELETE /{id}  取消任务 ────────────────────────────────────────────


@router.delete("/{task_id}", status_code=204)
async def cancel_task(
    task_id: UUID,
    task_repo: TaskRepository = Depends(get_task_repo),
):
    cancelled = await task_repo.cancel(str(task_id))
    if not cancelled:
        raise HTTPException(status_code=400, detail="任务无法取消（已完成或不存在）")


# ── 工具函数 ──────────────────────────────────────────────────────────


async def _sync_final_state(task_id: str, task_repo: TaskRepository):
    """流结束后将 Graph State 同步到 PostgreSQL"""
    try:
        from app.agents.runner import get_task_state
        from app.models.task import CostInfo, TaskResult

        state = await get_task_state(task_id)
        if not state:
            return

        result = state.get("result")
        if result and isinstance(result, TaskResult):
            await task_repo.update_result(
                task_id=task_id,
                result=result,
                cost=CostInfo(
                    token_input=state.get("token_input", 0),
                    token_output=state.get("token_output", 0),
                    cost_usd=state.get("cost_usd", 0.0),
                ),
                quality_score=state.get("quality_score", 0.0),
                iteration_count=state.get("iteration_count", 0),
            )
        elif state.get("error"):
            await task_repo.update_error(task_id, "AGENT_ERROR", state["error"])
    except Exception as e:
        import structlog

        structlog.get_logger().warning("同步最终状态失败", error=str(e))


async def _trigger_resume(task_id: str, approve_in: TaskApprove):
    """触发 HiTL resume（存入 Redis，SSE 重连时读取）"""
    try:
        import json

        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.redis_url)
        await r.setex(
            f"hitl_resume:{task_id}",
            settings.hitl_timeout_seconds,
            json.dumps(
                {
                    "action": approve_in.action,
                    "comment": approve_in.comment,
                    "modifications": approve_in.modifications,
                }
            ),
        )
        await r.aclose()
    except Exception as e:
        import structlog

        structlog.get_logger().warning("Redis HiTL resume 写入失败", error=str(e))
