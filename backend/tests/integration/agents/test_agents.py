"""
集成测试 — LangGraph Agent 节点（修复版 v4）

修复：
1. 节点函数返回 dict（LangGraph 规范），用 result["key"] 不是 result.key
2. retrieve 在 research_node 内部局部导入，patch 路径是 app.rag.retriever.retrieve
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock LLM 输出工厂 ─────────────────────────────────────────────────


def _llm_resp(content: str | dict) -> MagicMock:
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    resp = MagicMock()
    resp.content = content
    resp.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    resp.tool_calls = []
    return resp


def _planner_state(query: str = "分析2024年大模型市场", depth: str = "deep") -> dict:
    return {
        "task_id": "test-task-001",
        "user_id": "test-user-001",
        "user_query": query,
        "task_depth": depth,
    }


def _mock_memory():
    return MagicMock(
        build_memory_context=AsyncMock(return_value=""),
        find_related_history=AsyncMock(return_value=[]),
    )


# ══════════════════════════════════════════════════════════════════════
# TestPlannerAgent
# ══════════════════════════════════════════════════════════════════════


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_planner_generates_subtasks(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp(
                {
                    "summary": "市场竞争分析",
                    "sub_tasks": [
                        {"id": "t001", "description": "分析市场规模", "agent": "research"},
                        {"id": "t002", "description": "梳理竞争格局", "agent": "research"},
                        {"id": "t003", "description": "总结技术趋势", "agent": "research"},
                    ],
                    "estimated_steps": 5,
                    "requires_web_search": False,
                    "requires_sql_analysis": False,
                    "risk_level": "low",
                }
            )
        )

        with (
            patch("app.agents.nodes.get_planner_llm", return_value=mock_llm),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.nodes import planner_node

            result = await planner_node(_planner_state())

        # 节点返回 dict
        plan = result["plan"]
        assert plan is not None
        assert len(plan.sub_tasks) >= 1
        assert len(plan.sub_tasks) <= 10

    @pytest.mark.asyncio
    async def test_planner_sets_hitl_flag(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp(
                {
                    "summary": "测试",
                    "sub_tasks": [],
                    "estimated_steps": 2,
                    "risk_level": "low",
                }
            )
        )

        with (
            patch("app.agents.nodes.get_planner_llm", return_value=mock_llm),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
            patch("app.config.settings.hitl_enabled", True),
        ):
            from app.agents.nodes import planner_node

            result = await planner_node(_planner_state(depth="deep"))

        assert result["hitl_required"] is True

    @pytest.mark.asyncio
    async def test_planner_depth_quick_skips_hitl(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp(
                {
                    "summary": "快速分析",
                    "sub_tasks": [],
                    "estimated_steps": 1,
                    "risk_level": "low",
                }
            )
        )

        with (
            patch("app.agents.nodes.get_planner_llm", return_value=mock_llm),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.nodes import planner_node

            result = await planner_node(_planner_state(depth="quick"))

        assert result["hitl_required"] is False

    @pytest.mark.asyncio
    async def test_planner_handles_llm_json_error(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp("抱歉，我无法处理这个请求，请稍后重试。")
        )

        with (
            patch("app.agents.nodes.get_planner_llm", return_value=mock_llm),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.nodes import planner_node

            result = await planner_node(_planner_state())

        # JSON 解析失败时 fallback 到单任务
        assert result["plan"] is not None
        assert len(result["plan"].sub_tasks) >= 1

    @pytest.mark.asyncio
    async def test_planner_empty_query(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_resp({}))

        with (
            patch("app.agents.nodes.get_planner_llm", return_value=mock_llm),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.nodes import planner_node

            result = await planner_node(
                {
                    "task_id": "t",
                    "user_id": "u",
                    "user_query": "",
                    "task_depth": "quick",
                }
            )

        assert result is not None


# ══════════════════════════════════════════════════════════════════════
# TestResearchAgent
# ══════════════════════════════════════════════════════════════════════


class TestResearchAgent:
    def _research_state(self, n_tasks: int = 1, status: str = "pending") -> dict:
        from app.models.task import SubTask

        return {
            "task_id": "test-task-001",
            "user_id": "test-user-001",
            "user_query": "大模型市场分析",
            "task_depth": "deep",
            "sub_tasks": [
                SubTask(
                    id=f"t{i:03d}",
                    description=f"研究子任务{i}",
                    agent="research",
                    status=status,
                )
                for i in range(1, n_tasks + 1)
            ],
            "research_results": [],
        }

    def _mock_chunk(self):
        c = MagicMock()
        c.text = "大模型市场2024年规模超过千亿美元"
        c.title = "AI市场报告"
        c.source_url = None
        c.source_type = "internal"
        c.score = 0.92
        c.metadata = {}
        return c

    @pytest.mark.asyncio
    async def test_research_retrieves_from_kb(self, mock_llm):
        tool_resp = MagicMock()
        tool_resp.content = ""
        tool_resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        tool_resp.tool_calls = [
            {
                "id": "tc001",
                "name": "search_knowledge_base",
                "args": {"query": "大模型市场", "top_k": 5},
            }
        ]
        final_resp = _llm_resp("检索完成。")

        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=[tool_resp, final_resp])

        # retrieve 在 research_node 内部局部导入：from app.rag.retriever import retrieve
        with (
            patch("app.agents.nodes.get_research_llm", return_value=mock_llm),
            patch(
                "app.rag.retriever.retrieve",
                AsyncMock(return_value=MagicMock(chunks=[self._mock_chunk()])),
            ),
        ):
            from app.agents.nodes import research_node

            result = await research_node(self._research_state())

        assert result["research_results"] is not None

    @pytest.mark.asyncio
    async def test_research_parallel_queries(self, mock_llm):
        tool_resp = MagicMock()
        tool_resp.content = ""
        tool_resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        tool_resp.tool_calls = [
            {
                "id": "tc001",
                "name": "search_knowledge_base",
                "args": {"query": "查询1", "top_k": 3},
            }
        ]
        final_resp = _llm_resp("完成")

        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(side_effect=[tool_resp, final_resp])

        retrieve_call_count = 0

        async def count_retrieve(*args, **kwargs):
            nonlocal retrieve_call_count
            retrieve_call_count += 1
            return MagicMock(chunks=[])

        with (
            patch("app.agents.nodes.get_research_llm", return_value=mock_llm),
            patch("app.rag.retriever.retrieve", count_retrieve),
        ):
            from app.agents.nodes import research_node

            await research_node(self._research_state(n_tasks=3))

        assert retrieve_call_count >= 1

    @pytest.mark.asyncio
    async def test_research_no_pending_tasks_returns_empty(self, mock_llm):
        with patch("app.agents.nodes.get_research_llm", return_value=mock_llm):
            from app.agents.nodes import research_node

            result = await research_node(self._research_state(n_tasks=1, status="done"))

        assert result["research_results"] == []
        assert result["token_input"] == 0


# ══════════════════════════════════════════════════════════════════════
# TestWriterAgent
# ══════════════════════════════════════════════════════════════════════


class TestWriterAgent:
    SAMPLE_REPORT = """# 2024年大模型市场分析报告

## 摘要
2024年全球大模型市场规模突破千亿美元，增速超过预期。

## 市场规模
根据检索到的信息，市场呈现高速增长态势，头部厂商持续扩张。

## 竞争格局
头部厂商包括 OpenAI、Anthropic、Google，国内有阿里、百度。

## 结论
大模型市场将持续高速增长，国内外竞争加剧，差异化是关键。

## 参考来源
- [1] AI市场报告2024
- [2] IDC研究数据
"""

    def _writer_state(self, n_results: int = 2) -> dict:
        from app.models.task import SearchResult

        return {
            "task_id": "test-task-001",
            "user_id": "test-user-001",
            "user_query": "大模型市场分析",
            "task_depth": "deep",
            "structured_data": {"analysis": "市场高速增长，竞争加剧"},
            "research_results": [
                SearchResult(
                    text=f"市场数据第{i}条",
                    source=f"来源{i}",
                    source_type="internal",
                    score=0.9,
                )
                for i in range(1, n_results + 1)
            ],
            "critic_feedback": None,
        }

    @pytest.mark.asyncio
    async def test_writer_generates_markdown(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_resp(self.SAMPLE_REPORT))

        with patch("app.agents.nodes.get_writer_llm", return_value=mock_llm):
            from app.agents.nodes import writer_node

            result = await writer_node(self._writer_state())

        assert result["draft_report"] is not None
        assert "#" in result["draft_report"]
        assert len(result["draft_report"]) > 100

    @pytest.mark.asyncio
    async def test_writer_includes_sources(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_resp(self.SAMPLE_REPORT))

        with patch("app.agents.nodes.get_writer_llm", return_value=mock_llm):
            from app.agents.nodes import writer_node

            result = await writer_node(self._writer_state())

        report = result["draft_report"]
        assert "参考" in report or "来源" in report or "Source" in report

    @pytest.mark.asyncio
    async def test_writer_empty_chunks_handled(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp("# 报告\n\n暂无相关数据，建议扩充知识库。")
        )

        with patch("app.agents.nodes.get_writer_llm", return_value=mock_llm):
            from app.agents.nodes import writer_node

            state = self._writer_state(n_results=0)
            state["structured_data"] = {}
            result = await writer_node(state)

        assert result["draft_report"] is not None


# ══════════════════════════════════════════════════════════════════════
# TestCriticAgent
# ══════════════════════════════════════════════════════════════════════


class TestCriticAgent:
    def _critic_state(self, iteration: int = 0) -> dict:
        from app.models.task import SearchResult

        return {
            "task_id": "test-task-001",
            "user_id": "test-user-001",
            "user_query": "大模型市场分析",
            "task_depth": "deep",
            "draft_report": "# 报告\n\n市场分析内容...\n\n## 来源\n- [1] 测试",
            "research_results": [
                SearchResult(
                    text="市场数据",
                    source="来源1",
                    source_type="internal",
                    score=0.9,
                )
            ],
            "iteration_count": iteration,
        }

    @pytest.mark.asyncio
    async def test_critic_approves_good_report(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp(
                {
                    "score": 0.88,
                    "faithfulness": 0.90,
                    "completeness": 0.85,
                    "coherence": 0.88,
                    "actionability": 0.87,
                    "passed": True,
                    "feedback": "报告质量优秀，无需修改",
                    "flags": [],
                }
            )
        )

        # nodes.py 顶部 from app.agents.llm_factory import get_critic_llm
        # 必须 patch nodes 模块里已绑定的那个名字
        with patch("app.agents.nodes.get_critic_llm", return_value=mock_llm):
            from app.agents.nodes import critic_node

            result = await critic_node(self._critic_state())

        assert result["quality_score"] >= 0.8
        # 源码：passed=True 时 critic_feedback=None
        assert result["critic_feedback"] is None

    @pytest.mark.asyncio
    async def test_critic_requests_revision(self, mock_llm):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_resp(
                {
                    "score": 0.55,
                    "faithfulness": 0.50,
                    "completeness": 0.60,
                    "coherence": 0.55,
                    "actionability": 0.55,
                    "passed": False,
                    "feedback": "缺少数据支撑，建议补充市场规模数据",
                    "flags": ["missing_data"],
                }
            )
        )

        with patch("app.agents.nodes.get_critic_llm", return_value=mock_llm):
            from app.agents.nodes import critic_node

            result = await critic_node(self._critic_state())

        assert result["critic_feedback"] is not None
        assert result["quality_score"] < 0.7

    @pytest.mark.asyncio
    async def test_critic_max_iterations_stops_loop(self, mock_llm):
        """route_after_critic：iteration >= max 时强制路由到 finalize"""
        from app.agents.graph import route_after_critic
        from app.config import settings

        state = {
            "quality_score": 0.60,
            "iteration_count": settings.max_critic_iterations,
        }
        assert route_after_critic(state) == "finalize"


# ══════════════════════════════════════════════════════════════════════
# TestLangGraphWorkflow
# ══════════════════════════════════════════════════════════════════════


class TestLangGraphWorkflow:
    def _make_mock_graph(self, events: list[dict]):
        async def _astream_events(*args, **kwargs):
            for e in events:
                yield e

        graph = MagicMock()
        graph.astream_events = _astream_events
        graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
        return graph

    @pytest.mark.asyncio
    async def test_happy_path_completes(self):
        from app.models.task import TaskResult

        task_result = TaskResult(
            report="# 报告\n\n测试内容\n\n## 来源\n- [1] 测试",
            summary="测试摘要",
            sources=[],
            quality_score=0.87,
            word_count=50,
        )

        mock_events = [
            {"event": "on_chain_start", "name": "planner", "data": {}},
            {"event": "on_chain_start", "name": "research", "data": {}},
            {"event": "on_chain_start", "name": "writer", "data": {}},
            {"event": "on_chain_start", "name": "critic", "data": {}},
            {"event": "on_chain_start", "name": "finalize", "data": {}},
            {
                "event": "on_chain_end",
                "name": "finalize",
                "data": {"output": {"result": task_result}},
            },
        ]

        with (
            patch("app.agents.runner.get_graph", return_value=self._make_mock_graph(mock_events)),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.runner import run_research_stream

            events = []
            async for chunk in run_research_stream(
                task_id="test-task-001",
                user_id="test-user",
                query="2024年AI芯片市场分析",
                depth="quick",
            ):
                events.append(chunk)

        assert len(events) > 0
        all_text = "\n".join(events)
        assert "task_progress" in all_text or "task_completed" in all_text

    @pytest.mark.asyncio
    async def test_hitl_pause_resume(self):
        mock_events = [
            {"event": "on_chain_start", "name": "planner", "data": {}},
            {
                "event": "on_chain_end",
                "name": "__interrupt__",
                "data": {"output": {"plan": {"summary": "测试计划"}}},
            },
        ]

        with (
            patch("app.agents.runner.get_graph", return_value=self._make_mock_graph(mock_events)),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.runner import run_research_stream

            events = []
            async for chunk in run_research_stream(
                task_id="test-hitl-001",
                user_id="test-user",
                query="需要审批的任务",
                depth="deep",
            ):
                events.append(chunk)

        assert any("hitl_required" in e for e in events)

    @pytest.mark.asyncio
    async def test_workflow_handles_llm_timeout(self):
        async def _failing_stream(*args, **kwargs):
            raise TimeoutError("LLM API 超时")
            yield

        mock_graph = MagicMock()
        mock_graph.astream_events = _failing_stream

        with (
            patch("app.agents.runner.get_graph", return_value=mock_graph),
            patch("app.memory.store.get_memory_store", return_value=_mock_memory()),
        ):
            from app.agents.runner import run_research_stream

            events = []
            async for chunk in run_research_stream(
                task_id="test-timeout",
                user_id="test-user",
                query="超时测试",
                depth="quick",
            ):
                events.append(chunk)

        assert any("task_failed" in e for e in events)
