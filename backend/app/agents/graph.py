"""
ResearchMind Pro — LangGraph 工作流定义

节点流程：
  START
    └─► planner
          ├─► hitl（deep 模式，等用户确认）
          │     └─► research（approve 后继续）
          └─► research（quick 模式，直接进入）
                └─► analyst
                      └─► writer
                            └─► critic
                                  ├─► writer（score < threshold，重写）
                                  └─► finalize（score >= threshold）
                                        └─► END
"""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    analyst_node,
    critic_node,
    finalize_node,
    hitl_node,
    planner_node,
    research_node,
    writer_node,
)
from app.config import settings
from app.models.agent import ResearchState

# ── 路由函数 ──────────────────────────────────────────────────────────


def route_after_planner(
    state: ResearchState,
) -> Literal["hitl", "research"]:
    """
    Planner 后路由：
    - deep 模式 + hitl_enabled → hitl（等用户确认计划）
    - quick 模式或 hitl 禁用  → 直接 research
    """
    if state.get("hitl_required") and settings.hitl_enabled:
        return "hitl"
    return "research"


def route_after_hitl(
    state: ResearchState,
) -> Literal["research", END]:
    """
    HiTL 后路由：
    - 用户 approve  → research
    - 用户 reject   → END（取消任务）
    """
    if state.get("human_approved"):
        return "research"
    return END


def route_after_critic(
    state: ResearchState,
) -> Literal["writer", "finalize"]:
    """
    Critic 后路由：
    - 评分未达标 且 未超过最大迭代次数 → writer（重写）
    - 评分达标 或 超过最大迭代次数    → finalize
    """
    score = state.get("quality_score") or 0.0
    iteration = state.get("iteration_count", 0)
    max_iter = settings.max_critic_iterations

    if score < settings.min_quality_score and iteration < max_iter:
        return "writer"
    return "finalize"


# ── 构建 Graph ────────────────────────────────────────────────────────


def build_graph(checkpointer=None) -> StateGraph:
    """
    构建并编译 ResearchMind StateGraph。

    Args:
        checkpointer: LangGraph Checkpointer，用于状态持久化。
                      None → 使用 MemorySaver（仅内存，重启丢失）
    """
    graph = StateGraph(ResearchState)

    # ── 添加节点 ──────────────────────────────────────────────────────
    graph.add_node("planner", planner_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("research", research_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("writer", writer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("finalize", finalize_node)

    # ── 添加边 ────────────────────────────────────────────────────────
    graph.add_edge(START, "planner")

    # Planner → 条件路由
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"hitl": "hitl", "research": "research"},
    )

    # HiTL → 条件路由
    graph.add_conditional_edges(
        "hitl",
        route_after_hitl,
        {"research": "research", END: END},
    )

    # 线性流程
    graph.add_edge("research", "analyst")
    graph.add_edge("analyst", "writer")
    graph.add_edge("writer", "critic")

    # Critic → 条件路由（重写 or 完成）
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"writer": "writer", "finalize": "finalize"},
    )

    graph.add_edge("finalize", END)

    # ── 编译 ──────────────────────────────────────────────────────────
    cp = checkpointer or MemorySaver()
    return graph.compile(
        checkpointer=cp,
        interrupt_before=["hitl"],  # hitl 节点前自动暂停，等待外部 resume
    )


# ── Checkpointer 工厂 ─────────────────────────────────────────────────


async def create_checkpointer():
    """
    根据配置创建 Checkpointer。
    postgres：生产推荐，支持 HiTL 跨请求恢复。
    memory：开发调试用，重启后丢失。
    """
    if settings.checkpointer_backend == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            saver = AsyncPostgresSaver.from_conn_string(settings.postgres_url_sync)
            await saver.setup()  # 自动创建 checkpoints 表
            return saver
        except Exception as e:
            print(f"⚠️  PostgreSQL Checkpointer 初始化失败，降级到 MemorySaver: {e}")

    return MemorySaver()


# ── 全局单例 ──────────────────────────────────────────────────────────
# 由 FastAPI lifespan 在应用启动时初始化
_graph_instance = None


def get_graph():
    """获取编译好的 Graph 实例（需先调用 init_graph）"""
    global _graph_instance
    if _graph_instance is None:
        # 开发环境 fallback：使用 MemorySaver
        _graph_instance = build_graph(MemorySaver())
    return _graph_instance


async def init_graph():
    """应用启动时调用，初始化带 Checkpointer 的 Graph"""
    global _graph_instance
    checkpointer = await create_checkpointer()
    _graph_instance = build_graph(checkpointer)
    print(f"✅ LangGraph 初始化完成（checkpointer: {settings.checkpointer_backend}）")
    return _graph_instance
