"""
任务（Task）相关 Pydantic 模型
涵盖：创建/响应/状态更新/HiTL 审批/SSE 事件
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# ── 枚举 ──────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING      = "pending"
    PLANNING     = "planning"
    RESEARCHING  = "researching"
    ANALYZING    = "analyzing"
    WRITING      = "writing"
    REVIEWING    = "reviewing"
    COMPLETED    = "completed"
    FAILED       = "failed"
    CANCELLED    = "cancelled"


class TaskDepth(str, Enum):
    QUICK = "quick"   # 快速模式：2 轮检索，跳过 Critic
    DEEP  = "deep"    # 深度模式：5 轮检索，完整 Critic 循环


class SSEEventType(str, Enum):
    TASK_STARTED    = "task_started"
    AGENT_THOUGHT   = "agent_thought"
    TOOL_CALL       = "tool_call"
    TOOL_RESULT     = "tool_result"
    HITL_REQUIRED   = "hitl_required"
    TASK_PROGRESS   = "task_progress"
    TASK_COMPLETED  = "task_completed"
    TASK_FAILED     = "task_failed"


# ── 子模型 ────────────────────────────────────────────────────────────

class SubTask(BaseModel):
    """Planner 分解出的子任务"""
    id:          str = Field(default_factory=lambda: str(uuid4())[:8])
    description: str
    agent:       str   # planner / research / analyst / writer / critic
    depends_on:  list[str] = []
    status:      str = "pending"


class TaskPlan(BaseModel):
    """Planner Agent 的输出"""
    summary:        str
    sub_tasks:      list[SubTask]
    estimated_steps: int = 0
    requires_web_search:   bool = False
    requires_sql_analysis: bool = False
    risk_level:     str = "low"   # low / medium / high


class SearchResult(BaseModel):
    """单条检索结果"""
    text:        str
    source:      str           # URL 或文档名
    source_type: str = "internal"   # internal / web
    score:       float = 0.0
    metadata:    dict[str, Any] = {}


class TaskResult(BaseModel):
    """任务最终输出"""
    report:        str           # Markdown 格式报告
    summary:       str           # 一句话摘要
    sources:       list[SearchResult] = []
    quality_score: float = 0.0
    word_count:    int = 0


class CostInfo(BaseModel):
    """Token 成本信息"""
    token_input:  int   = 0
    token_output: int   = 0
    cost_usd:     float = 0.0


# ── API 请求模型 ──────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    """POST /api/v1/tasks 请求体"""
    query:   str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="研究问题或任务描述",
        examples=["分析 2025 年大模型行业的主要竞争格局和技术趋势"]
    )
    depth:   TaskDepth = TaskDepth.DEEP
    context: dict[str, Any] = Field(
        default={},
        description="补充上下文，如领域、语言偏好等"
    )

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query 不能为空")
        return v


class TaskApprove(BaseModel):
    """POST /api/v1/tasks/{id}/approve 请求体"""
    action:        str = Field(..., pattern="^(approve|modify|reject)$")
    modifications: dict[str, Any] = Field(
        default={},
        description="action=modify 时传入修改内容，如 {plan: {...}}"
    )
    comment:       str = ""


# ── API 响应模型 ──────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    """任务基本信息响应"""
    id:          UUID
    status:      TaskStatus
    query:       str
    depth:       TaskDepth
    created_at:  datetime
    started_at:  datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskDetailResponse(TaskResponse):
    """任务详情响应（含结果）"""
    plan:           TaskPlan | None = None
    result:         TaskResult | None = None
    quality_score:  float | None = None
    iteration_count: int = 0
    hitl_required:  bool = False
    cost:           CostInfo = CostInfo()
    error_message:  str | None = None

    # 进度（0~100）
    @property
    def progress(self) -> int:
        progress_map = {
            TaskStatus.PENDING:     0,
            TaskStatus.PLANNING:    10,
            TaskStatus.RESEARCHING: 35,
            TaskStatus.ANALYZING:   55,
            TaskStatus.WRITING:     70,
            TaskStatus.REVIEWING:   85,
            TaskStatus.COMPLETED:   100,
            TaskStatus.FAILED:      0,
            TaskStatus.CANCELLED:   0,
        }
        return progress_map.get(self.status, 0)


class TaskListResponse(BaseModel):
    """任务列表响应"""
    items: list[TaskResponse]
    total: int
    page:  int = 1
    size:  int = 20


# ── SSE 事件模型 ──────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    """SSE 流式事件基类"""
    event:     SSEEventType
    task_id:   str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data:      dict[str, Any] = {}

    def to_sse(self) -> str:
        """序列化为 SSE 格式字符串"""
        import json
        payload = self.model_dump(mode="json")
        return f"event: {self.event.value}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class AgentThoughtEvent(SSEEvent):
    """Agent 推理过程事件"""
    event: SSEEventType = SSEEventType.AGENT_THOUGHT

    @classmethod
    def create(cls, task_id: str, agent: str, thought: str) -> "AgentThoughtEvent":
        return cls(task_id=task_id, data={"agent": agent, "thought": thought})


class ToolCallEvent(SSEEvent):
    """工具调用事件"""
    event: SSEEventType = SSEEventType.TOOL_CALL

    @classmethod
    def create(cls, task_id: str, agent: str, tool: str, input_data: dict) -> "ToolCallEvent":
        return cls(task_id=task_id, data={"agent": agent, "tool": tool, "input": input_data})


class ToolResultEvent(SSEEvent):
    """工具返回事件"""
    event: SSEEventType = SSEEventType.TOOL_RESULT

    @classmethod
    def create(cls, task_id: str, agent: str, tool: str, result: Any) -> "ToolResultEvent":
        return cls(task_id=task_id, data={"agent": agent, "tool": tool, "result": str(result)[:500]})


class HiTLRequiredEvent(SSEEvent):
    """HiTL 中断事件：要求用户审批"""
    event: SSEEventType = SSEEventType.HITL_REQUIRED

    @classmethod
    def create(cls, task_id: str, plan: dict, reason: str, timeout: int = 300) -> "HiTLRequiredEvent":
        return cls(task_id=task_id, data={"plan": plan, "reason": reason, "timeout_seconds": timeout})


class TaskProgressEvent(SSEEvent):
    """任务进度更新事件"""
    event: SSEEventType = SSEEventType.TASK_PROGRESS

    @classmethod
    def create(cls, task_id: str, status: str, progress: int, message: str = "") -> "TaskProgressEvent":
        return cls(task_id=task_id, data={"status": status, "progress": progress, "message": message})


class TaskCompletedEvent(SSEEvent):
    """任务完成事件"""
    event: SSEEventType = SSEEventType.TASK_COMPLETED

    @classmethod
    def create(cls, task_id: str, result: TaskResult, cost: CostInfo) -> "TaskCompletedEvent":
        return cls(task_id=task_id, data={
            "report":        result.report,
            "summary":       result.summary,
            "sources":       [s.model_dump() for s in result.sources],
            "quality_score": result.quality_score,
            "cost_usd":      cost.cost_usd,
        })


class TaskFailedEvent(SSEEvent):
    """任务失败事件"""
    event: SSEEventType = SSEEventType.TASK_FAILED

    @classmethod
    def create(cls, task_id: str, error_code: str, message: str) -> "TaskFailedEvent":
        return cls(task_id=task_id, data={"error_code": error_code, "message": message})
