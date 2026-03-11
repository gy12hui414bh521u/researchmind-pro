"""
Graph Runner — 封装 LangGraph 的执行、流式输出、HiTL resume
供 FastAPI 路由层调用，隔离 LangGraph 细节
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.agents.graph import get_graph
from app.config import settings
from app.models.agent import create_initial_state
from app.models.task import (
    AgentThoughtEvent,
    CostInfo,
    HiTLRequiredEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskProgressEvent,
    TaskResult,
)

# ── 进度映射 ──────────────────────────────────────────────────────────

_NODE_PROGRESS = {
    "planner": 15,
    "hitl": 20,
    "research": 45,
    "analyst": 60,
    "writer": 75,
    "critic": 88,
    "finalize": 95,
}

_NODE_LABEL = {
    "planner": "Planner 正在分解任务...",
    "hitl": "等待用户确认研究计划",
    "research": "Research 正在检索知识库...",
    "analyst": "Analyst 正在分析资料...",
    "writer": "Writer 正在撰写报告...",
    "critic": "Critic 正在评审报告...",
    "finalize": "正在整理最终结果...",
}


# ── 主执行函数（SSE 流式）────────────────────────────────────────────


async def run_research_stream(
    task_id: str,
    user_id: str,
    query: str,
    depth: str = "deep",
) -> AsyncGenerator[str, None]:
    """
    启动研究任务，以 SSE 格式流式输出进度事件。
    供 FastAPI StreamingResponse 使用。

    Yields:
        SSE 格式字符串，如 "event: task_progress\ndata: {...}\n\n"
    """
    graph = get_graph()
    config = {
        "configurable": {"thread_id": task_id},
        "recursion_limit": settings.graph_recursion_limit,
    }

    # 注入长期记忆：历史相关任务摘要
    from app.memory.store import get_memory_store

    memory = get_memory_store()
    try:
        related = await memory.find_related_history(user_id, query, limit=3)
        if related:
            history_ctx = "\n\n【历史相关研究参考】\n" + "\n".join(
                f"- {r['query']}: {r['summary']}" for r in related
            )
            enriched_query = query + history_ctx
        else:
            enriched_query = query
    except Exception:
        enriched_query = query

    initial_state = create_initial_state(
        task_id=task_id,
        user_id=user_id,
        user_query=enriched_query,
        task_depth=depth,
    )

    try:
        # 发送开始事件
        yield TaskProgressEvent.create(
            task_id=task_id, status="planning", progress=5, message="任务已启动，Planner 准备中..."
        ).to_sse()

        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            event_type = event.get("event", "")
            node_name = event.get("name", "")
            data = event.get("data", {})

            # 节点开始
            if event_type == "on_chain_start" and node_name in _NODE_PROGRESS:
                yield TaskProgressEvent.create(
                    task_id=task_id,
                    status=node_name,
                    progress=_NODE_PROGRESS[node_name],
                    message=_NODE_LABEL.get(node_name, f"{node_name} 执行中..."),
                ).to_sse()

            # LLM token 流（思考过程）
            elif event_type == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield AgentThoughtEvent.create(
                        task_id=task_id,
                        agent=node_name or "agent",
                        thought=chunk.content,
                    ).to_sse()

            # HiTL 中断
            elif event_type == "on_chain_end" and node_name == "__interrupt__":
                interrupt_data = data.get("output", {})
                plan = (interrupt_data or {}).get("plan", {})
                yield HiTLRequiredEvent.create(
                    task_id=task_id,
                    plan=plan,
                    reason="请确认研究计划后继续执行",
                    timeout=settings.hitl_timeout_seconds,
                ).to_sse()
                return  # 暂停，等待 resume

            # 节点完成，检查是否有最终结果
            elif event_type == "on_chain_end" and node_name == "finalize":
                output = data.get("output", {})
                result = output.get("result")
                if result and isinstance(result, TaskResult):
                    state = await _get_latest_state(graph, config)
                    cost = _extract_cost(state)
                    yield TaskCompletedEvent.create(
                        task_id=task_id,
                        result=result,
                        cost=cost,
                    ).to_sse()
                    return

    except Exception as e:
        yield TaskFailedEvent.create(
            task_id=task_id,
            error_code="GRAPH_ERROR",
            message=str(e),
        ).to_sse()


# ── HiTL Resume ───────────────────────────────────────────────────────


async def resume_after_hitl(
    task_id: str,
    action: str,  # approve | modify | reject
    comment: str = "",
) -> AsyncGenerator[str, None]:
    """
    用户审批后恢复 Graph 执行，继续流式输出。
    """
    graph = get_graph()
    config = {
        "configurable": {"thread_id": task_id},
        "recursion_limit": settings.graph_recursion_limit,
    }

    # 恢复数据传给 interrupt()
    resume_data = {"action": action, "comment": comment}

    try:
        async for event in graph.astream_events(resume_data, config=config, version="v2"):
            event_type = event.get("event", "")
            node_name = event.get("name", "")
            data = event.get("data", {})

            if event_type == "on_chain_start" and node_name in _NODE_PROGRESS:
                yield TaskProgressEvent.create(
                    task_id=task_id,
                    status=node_name,
                    progress=_NODE_PROGRESS[node_name],
                    message=_NODE_LABEL.get(node_name, ""),
                ).to_sse()

            elif event_type == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield AgentThoughtEvent.create(
                        task_id=task_id,
                        agent=node_name or "agent",
                        thought=chunk.content,
                    ).to_sse()

            elif event_type == "on_chain_end" and node_name == "finalize":
                output = data.get("output", {})
                result = output.get("result")
                if result:
                    state = await _get_latest_state(graph, config)
                    cost = _extract_cost(state)
                    yield TaskCompletedEvent.create(
                        task_id=task_id,
                        result=result,
                        cost=cost,
                    ).to_sse()
                    return

    except Exception as e:
        yield TaskFailedEvent.create(
            task_id=task_id,
            error_code="RESUME_ERROR",
            message=str(e),
        ).to_sse()


# ── 工具函数 ──────────────────────────────────────────────────────────


async def _get_latest_state(graph, config: dict) -> dict:
    """获取 Graph 最新 State 快照"""
    try:
        snapshot = await graph.aget_state(config)
        return snapshot.values if snapshot else {}
    except Exception:
        return {}


def _extract_cost(state: dict) -> CostInfo:
    return CostInfo(
        token_input=state.get("token_input", 0),
        token_output=state.get("token_output", 0),
        cost_usd=state.get("cost_usd", 0.0),
    )


async def get_task_state(task_id: str) -> dict:
    """获取任务当前状态（供 API 查询用）"""
    graph = get_graph()
    config = {"configurable": {"thread_id": task_id}}
    return await _get_latest_state(graph, config)


async def save_task_to_memory(user_id: str, task_id: str, query: str, result) -> None:
    """任务完成后将摘要写入长期记忆"""
    try:
        from app.memory.store import get_memory_store

        memory = get_memory_store()
        summary = getattr(result, "summary", "") or ""
        # 简单提取关键词（取 query 前几个词）
        keywords = [w for w in query.split() if len(w) > 1][:8]
        await memory.save_task_summary(
            user_id=user_id,
            task_id=task_id,
            query=query,
            summary=summary,
            keywords=keywords,
        )
    except Exception:
        pass  # 记忆写入失败不影响主流程
