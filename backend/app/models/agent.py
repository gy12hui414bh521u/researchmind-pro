"""
LangGraph State 及 Agent 内部通信模型
ResearchState 是整个 Multi-Agent 工作流的核心数据结构
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.models.task import SearchResult, SubTask, TaskPlan

# ══════════════════════════════════════════════════════════════════════
# LangGraph State — 整个工作流的共享状态
# Annotated[list, operator.add] 表示该字段使用 append reducer
# （并行节点写入时自动合并，而非覆盖）
# ══════════════════════════════════════════════════════════════════════


class ResearchState(TypedDict):
    # ── 任务基本信息 ──────────────────────────────────────────────────
    task_id: str
    user_id: str
    user_query: str
    task_depth: str  # quick | deep

    # ── Planner 输出 ──────────────────────────────────────────────────
    plan: TaskPlan | None
    sub_tasks: Annotated[list[SubTask], operator.add]  # append

    # ── Research 输出（并行写入，append reducer 自动合并）─────────────
    research_results: Annotated[list[SearchResult], operator.add]

    # ── Analyst 输出 ──────────────────────────────────────────────────
    structured_data: dict[str, Any] | None  # DataFrame 序列化为 dict
    sql_query: str | None  # 记录执行的 SQL

    # ── Writer/Critic 迭代 ────────────────────────────────────────────
    draft_report: str | None
    quality_score: float | None
    critic_feedback: str | None  # Critic 的改进建议，注入下一轮 Writer
    iteration_count: int  # 防无限循环，最大 MAX_CRITIC_ITERATIONS

    # ── HiTL 控制 ─────────────────────────────────────────────────────
    hitl_required: bool
    human_approved: bool
    human_feedback: str | None  # 用户审批时的修改意见

    # ── 成本追踪 ──────────────────────────────────────────────────────
    token_input: int
    token_output: int
    cost_usd: float

    # ── 错误处理 ──────────────────────────────────────────────────────
    error: str | None
    error_code: str | None

    # ── LangChain Messages（工具调用历史）────────────────────────────
    # add_messages reducer：自动去重并按顺序追加
    messages: Annotated[list[BaseMessage], add_messages]


def create_initial_state(
    task_id: str,
    user_id: str,
    user_query: str,
    task_depth: str = "deep",
) -> ResearchState:
    """
    创建 ResearchState 初始值。
    所有字段必须有初始值，LangGraph 不允许缺字段。
    """
    return ResearchState(
        task_id=task_id,
        user_id=user_id,
        user_query=user_query,
        task_depth=task_depth,
        plan=None,
        sub_tasks=[],
        research_results=[],
        structured_data=None,
        sql_query=None,
        draft_report=None,
        quality_score=None,
        critic_feedback=None,
        iteration_count=0,
        hitl_required=False,
        human_approved=False,
        human_feedback=None,
        token_input=0,
        token_output=0,
        cost_usd=0.0,
        error=None,
        error_code=None,
        messages=[],
    )


# ── Agent 节点输出模型 ────────────────────────────────────────────────
# 每个 Agent 节点返回 ResearchState 的部分更新（partial state）
# LangGraph 会自动 merge 到全局 State


class PlannerOutput(TypedDict, total=False):
    """Planner 节点返回值"""

    plan: TaskPlan
    sub_tasks: list[SubTask]
    hitl_required: bool
    token_input: int
    token_output: int
    cost_usd: float
    messages: list[BaseMessage]


class ResearchOutput(TypedDict, total=False):
    """Research 节点返回值（并行时多个节点各自返回，reducer 合并）"""

    research_results: list[SearchResult]
    token_input: int
    token_output: int
    cost_usd: float
    messages: list[BaseMessage]


class AnalystOutput(TypedDict, total=False):
    """Analyst 节点返回值"""

    structured_data: dict[str, Any]
    sql_query: str
    token_input: int
    token_output: int
    cost_usd: float
    messages: list[BaseMessage]


class WriterOutput(TypedDict, total=False):
    """Writer 节点返回值"""

    draft_report: str
    token_input: int
    token_output: int
    cost_usd: float
    messages: list[BaseMessage]


class CriticOutput(TypedDict, total=False):
    """Critic 节点返回值"""

    quality_score: float
    critic_feedback: str
    iteration_count: int
    token_input: int
    token_output: int
    cost_usd: float
    messages: list[BaseMessage]


# ── 工具调用结果 ──────────────────────────────────────────────────────


class ToolCallResult(TypedDict):
    """统一的工具调用返回结构"""

    success: bool
    data: Any
    error: str | None
    latency_ms: int


# ── Critic 评估结构 ───────────────────────────────────────────────────


class CriticEvaluation(TypedDict):
    """Critic Agent 的结构化评估输出（要求 LLM 输出 JSON）"""

    score: float  # 0.0 ~ 1.0
    faithfulness: float  # 事实准确性
    completeness: float  # 任务覆盖度
    coherence: float  # 逻辑连贯性
    feedback: str  # 改进建议（注入下一轮 Writer）
    passed: bool  # score >= min_quality_score
    flags: list[str]  # 具体问题标记
