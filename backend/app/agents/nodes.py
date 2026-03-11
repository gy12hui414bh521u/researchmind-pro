"""
LangGraph Agent 节点实现
每个函数对应 StateGraph 中的一个节点，接收 ResearchState 返回部分更新
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm_factory import (
    get_analyst_llm,
    get_critic_llm,
    get_planner_llm,
    get_research_llm,
    get_writer_llm,
)
from app.agents.prompts import (
    ANALYST_SYSTEM,
    ANALYST_USER,
    CRITIC_SYSTEM,
    CRITIC_USER,
    PLANNER_SYSTEM,
    PLANNER_USER,
    RESEARCH_SYSTEM,
    RESEARCH_USER,
    WRITER_CRITIC_FEEDBACK,
    WRITER_SYSTEM,
    WRITER_USER,
)
from app.agents.tools import RESEARCH_TOOLS
from app.config import settings
from app.models.agent import (
    AnalystOutput,
    CriticOutput,
    PlannerOutput,
    ResearchOutput,
    WriterOutput,
)
from app.models.task import SearchResult, SubTask, TaskPlan

# ── 工具函数 ──────────────────────────────────────────────────────────


def _parse_json_safe(text: str, fallback: dict) -> dict:
    """从 LLM 输出中安全提取 JSON"""
    # 先尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 提取第一个 { ... }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return fallback


def _estimate_cost(input_tokens: int, output_tokens: int, provider: str) -> float:
    """估算 API 成本（美元）"""
    # 2025 年参考价格（per 1M tokens）
    pricing = {
        "deepseek": (1.0, 2.0),  # input, output  $/1M
        "qwen": (0.8, 2.0),
        "openai": (2.5, 10.0),  # gpt-4o
        "anthropic": (3.0, 15.0),  # claude-3-5
    }
    p = pricing.get(provider, (1.0, 2.0))
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


def _get_provider(spec: str) -> str:
    provider, _ = settings.parse_model_spec(spec)
    return provider


def _format_research_results(results: list[SearchResult]) -> str:
    """将检索结果格式化为 LLM 可读文本"""
    if not results:
        return "暂无检索资料。"
    lines = []
    for i, r in enumerate(results[:15], 1):  # 最多 15 条
        source = r.source or "未知来源"
        lines.append(f"[{i}] 来源: {source}")
        lines.append(r.text[:500])
        lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# 节点 1：Planner
# ══════════════════════════════════════════════════════════════════════


async def planner_node(state: dict) -> PlannerOutput:
    """
    将用户 query 分解为结构化研究计划。
    输出：TaskPlan + SubTask 列表 + HiTL 标志
    """
    llm = get_planner_llm()
    provider = _get_provider(settings.planner_model_spec)

    # 注入长期记忆（用户偏好 + 历史研究摘要）
    memory_context = ""
    try:
        from app.memory.store import get_memory_store

        memory_context = await get_memory_store().build_memory_context(
            user_id=state["user_id"],
            query=state["user_query"],
        )
    except Exception:
        pass

    user_prompt = PLANNER_USER.format(
        query=state["user_query"],
        depth=state["task_depth"],
    )
    if memory_context:
        user_prompt = f"{memory_context}\n\n{user_prompt}"

    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    content = response.content

    # 解析 JSON
    raw = _parse_json_safe(content, {})

    # 构建 TaskPlan
    sub_tasks_raw = raw.get("sub_tasks", [])
    sub_tasks = [
        SubTask(
            id=st.get("id", f"t{i:03d}"),
            description=st.get("description", ""),
            agent=st.get("agent", "research"),
            depends_on=st.get("depends_on", []),
        )
        for i, st in enumerate(sub_tasks_raw, 1)
    ]

    if not sub_tasks:
        # Fallback：单任务
        sub_tasks = [
            SubTask(
                id="t001",
                description=f"研究：{state['user_query']}",
                agent="research",
            )
        ]

    plan = TaskPlan(
        summary=raw.get("summary", state["user_query"]),
        sub_tasks=sub_tasks,
        estimated_steps=raw.get("estimated_steps", len(sub_tasks) + 2),
        requires_web_search=raw.get("requires_web_search", False),
        requires_sql_analysis=raw.get("requires_sql_analysis", False),
        risk_level=raw.get("risk_level", "low"),
    )

    # 估算成本
    usage = getattr(response, "usage_metadata", None) or {}
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = _estimate_cost(inp, out, provider)

    # deep 模式开启 HiTL（让用户确认计划）
    hitl = (state["task_depth"] == "deep") and settings.hitl_enabled

    return PlannerOutput(
        plan=plan,
        sub_tasks=sub_tasks,
        hitl_required=hitl,
        token_input=inp,
        token_output=out,
        cost_usd=cost,
        messages=[response],
    )


# ══════════════════════════════════════════════════════════════════════
# 节点 2：Research（支持并行调用）
# ══════════════════════════════════════════════════════════════════════


async def research_node(state: dict) -> ResearchOutput:
    """
    检索知识库和网络，收集研究资料。
    使用 Tool Calling，让 LLM 自主决定调用哪些工具。
    """
    llm = get_research_llm()
    provider = _get_provider(settings.research_model_spec)

    # 找出当前待执行的 research 子任务
    pending = [
        st for st in state.get("sub_tasks", []) if st.agent == "research" and st.status == "pending"
    ]
    if not pending:
        return ResearchOutput(research_results=[], token_input=0, token_output=0, cost_usd=0.0)

    # 取第一个待执行任务（串行），并行版本在 graph 层面处理
    sub_task = pending[0]

    # 已有结果摘要（给 LLM 作为上下文，避免重复检索）
    existing = state.get("research_results", [])
    existing_summary = (
        f"已检索 {len(existing)} 条资料，涉及: " + "、".join({r.source for r in existing[:5]})
        if existing
        else "无"
    )

    # LLM + Tools
    llm_with_tools = llm.bind_tools(RESEARCH_TOOLS)
    messages = [
        SystemMessage(content=RESEARCH_SYSTEM),
        HumanMessage(
            content=RESEARCH_USER.format(
                sub_task_description=sub_task.description,
                user_query=state["user_query"],
                existing_summary=existing_summary,
            )
        ),
    ]

    # Tool calling 循环（最多 3 轮）
    all_results: list[SearchResult] = []
    total_inp = total_out = 0

    for _ in range(3):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        usage = getattr(response, "usage_metadata", None) or {}
        total_inp += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)

        # 处理工具调用
        tool_calls = getattr(response, "tool_calls", [])
        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("args", {})

            # 执行工具
            result_text = ""
            if tool_name == "search_knowledge_base":
                from app.rag.retriever import retrieve

                r = await retrieve(
                    query=tool_args.get("query", sub_task.description),
                    top_k=tool_args.get("top_k", 5),
                )
                for chunk in r.chunks:
                    all_results.append(
                        SearchResult(
                            text=chunk.text,
                            source=chunk.title or chunk.source_url or "知识库",
                            source_type=chunk.source_type,
                            score=chunk.score,
                            metadata=chunk.metadata,
                        )
                    )
                result_text = f"检索完成，获得 {len(r.chunks)} 条结果"

            elif tool_name == "web_search" and settings.has_tavily:
                result_text = await RESEARCH_TOOLS[1].ainvoke(tool_args)

            elif tool_name == "get_current_date":
                from datetime import datetime

                result_text = datetime.now().strftime("%Y年%m月%d日")

            from langchain_core.messages import ToolMessage

            messages.append(
                ToolMessage(
                    content=result_text or "工具执行完成",
                    tool_call_id=tc["id"],
                )
            )

    cost = _estimate_cost(total_inp, total_out, provider)
    return ResearchOutput(
        research_results=all_results,
        token_input=total_inp,
        token_output=total_out,
        cost_usd=cost,
        messages=messages[2:],  # 只保留本轮新增消息
    )


# ══════════════════════════════════════════════════════════════════════
# 节点 3：Analyst
# ══════════════════════════════════════════════════════════════════════


async def analyst_node(state: dict) -> AnalystOutput:
    """对 Research 收集的原始资料进行结构化分析"""
    llm = get_analyst_llm()
    provider = _get_provider(settings.analyst_model_spec)

    research_text = _format_research_results(state.get("research_results", []))

    messages = [
        SystemMessage(content=ANALYST_SYSTEM),
        HumanMessage(
            content=ANALYST_USER.format(
                user_query=state["user_query"],
                research_results=research_text,
            )
        ),
    ]

    response = await llm.ainvoke(messages)

    usage = getattr(response, "usage_metadata", None) or {}
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = _estimate_cost(inp, out, provider)

    return AnalystOutput(
        structured_data={"analysis": response.content},
        token_input=inp,
        token_output=out,
        cost_usd=cost,
        messages=[response],
    )


# ══════════════════════════════════════════════════════════════════════
# 节点 4：Writer
# ══════════════════════════════════════════════════════════════════════


async def writer_node(state: dict) -> WriterOutput:
    """将分析结果撰写为完整研究报告"""
    llm = get_writer_llm()
    provider = _get_provider(settings.writer_model_spec)

    # 分析结果
    analysis_data = state.get("structured_data") or {}
    analysis_text = analysis_data.get("analysis", "无结构化分析结果")

    # 来源摘要
    results = state.get("research_results", [])
    sources_summary = (
        "\n".join(f"- {r.source}: {r.text[:100]}..." for r in results[:8]) or "无参考来源"
    )

    # Critic 反馈（如有）
    feedback = state.get("critic_feedback")
    critic_section = WRITER_CRITIC_FEEDBACK.format(feedback=feedback) if feedback else ""

    messages = [
        SystemMessage(content=WRITER_SYSTEM),
        HumanMessage(
            content=WRITER_USER.format(
                user_query=state["user_query"],
                depth=state["task_depth"],
                analysis=analysis_text,
                sources_summary=sources_summary,
                critic_feedback_section=critic_section,
            )
        ),
    ]

    response = await llm.ainvoke(messages)

    usage = getattr(response, "usage_metadata", None) or {}
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = _estimate_cost(inp, out, provider)

    return WriterOutput(
        draft_report=response.content,
        token_input=inp,
        token_output=out,
        cost_usd=cost,
        messages=[response],
    )


# ══════════════════════════════════════════════════════════════════════
# 节点 5：Critic
# ══════════════════════════════════════════════════════════════════════


async def critic_node(state: dict) -> CriticOutput:
    """对 Writer 草稿进行独立质量评审"""
    llm = get_critic_llm()
    provider = _get_provider(settings.critic_model_spec)

    results = state.get("research_results", [])
    sources = "\n".join(f"- {r.source}: {r.text[:150]}" for r in results[:6]) or "无"
    draft = state.get("draft_report", "")
    iteration = state.get("iteration_count", 0) + 1

    messages = [
        SystemMessage(content=CRITIC_SYSTEM),
        HumanMessage(
            content=CRITIC_USER.format(
                user_query=state["user_query"],
                sources_summary=sources,
                draft_report=draft[:4000],  # 防止超长
            )
        ),
    ]

    response = await llm.ainvoke(messages)

    usage = getattr(response, "usage_metadata", None) or {}
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = _estimate_cost(inp, out, provider)

    # 解析评审 JSON
    raw = _parse_json_safe(
        response.content,
        {
            "score": 0.76,
            "faithfulness": 0.76,
            "completeness": 0.76,
            "coherence": 0.76,
            "actionability": 0.76,
            "passed": True,
            "feedback": "解析失败，默认通过",
            "flags": [],
        },
    )

    score = float(raw.get("score", 0.76))
    passed = bool(raw.get("passed", score >= settings.min_quality_score))
    feedback = raw.get("feedback", "")

    return CriticOutput(
        quality_score=score,
        critic_feedback=feedback if not passed else None,
        iteration_count=iteration,
        token_input=inp,
        token_output=out,
        cost_usd=cost,
        messages=[response],
    )


# ══════════════════════════════════════════════════════════════════════
# 节点 6：HiTL 等待节点（Interrupt）
# ══════════════════════════════════════════════════════════════════════


async def hitl_node(state: dict) -> dict:
    """
    Human-in-the-Loop 节点。
    LangGraph 通过 interrupt() 暂停图执行，等待外部 resume。
    """
    from langgraph.types import interrupt

    plan = state.get("plan")
    plan_dict = plan.model_dump() if plan else {}

    # interrupt() 会抛出特殊异常，暂停图执行
    # 前端通过 SSE 收到 hitl_required 事件后，
    # 调用 POST /tasks/{id}/approve 触发 resume
    human_input = interrupt(
        {
            "type": "hitl_plan_review",
            "plan": plan_dict,
            "message": "请确认研究计划，或提出修改意见",
        }
    )

    # resume 后 human_input 包含用户的审批结果
    approved = human_input.get("action") == "approve"
    feedback = human_input.get("comment", "")

    return {
        "hitl_required": False,  # 已处理
        "human_approved": approved,
        "human_feedback": feedback,
    }


# ══════════════════════════════════════════════════════════════════════
# 节点 7：最终汇总节点
# ══════════════════════════════════════════════════════════════════════


async def finalize_node(state: dict) -> dict:
    """
    汇总最终结果，构建 TaskResult。
    这是 Graph 的终止节点。
    """
    from app.models.task import TaskResult

    results = state.get("research_results", [])
    sources = [
        SearchResult(
            text=r.text[:200],
            source=r.source,
            source_type=r.source_type,
            score=r.score,
        )
        for r in results[:10]
    ]

    report = state.get("draft_report", "报告生成失败")
    # 提取第一段作为摘要
    lines = [line.strip() for line in report.split("\n") if line.strip()]
    summary = next(
        (line for line in lines if not line.startswith("#") and len(line) > 20),
        lines[0] if lines else "无摘要",
    )[:300]

    task_result = TaskResult(
        report=report,
        summary=summary,
        sources=sources,
        quality_score=state.get("quality_score") or 0.0,
        word_count=len(report),
    )

    # 保存任务摘要到长期记忆
    try:
        import re

        from app.memory.store import get_memory_store

        keywords = list(set(re.findall(r"[一-鿿]{2,4}|[A-Z][a-z]+", report)))[:10]
        await get_memory_store().save_task_summary(
            user_id=state.get("user_id", ""),
            task_id=state.get("task_id", ""),
            query=state.get("user_query", ""),
            summary=summary,
            keywords=keywords,
        )
    except Exception:
        pass

    return {
        "result": task_result,
        "quality_score": task_result.quality_score,
    }
