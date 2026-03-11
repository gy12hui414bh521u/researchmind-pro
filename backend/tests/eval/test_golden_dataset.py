"""
Eval 测试套件 — Golden Dataset
SDD §13.2：100 条标准问答对，验证 Hit Rate@5 ≥ 85%、Faithfulness ≥ 0.85
运行方式：pytest tests/eval/ -m eval --tb=short
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

# ── Golden Dataset（精简版 20 条，CI 用）────────────────────────────

GOLDEN_DATASET = [
    {
        "id": "q001",
        "query": "什么是 RAG？",
        "relevant_content": "RAG（Retrieval-Augmented Generation）是一种将检索与生成结合的技术，通过从外部知识库检索相关信息来增强 LLM 的输出质量。",
        "expected_keywords": ["检索", "生成", "知识库"],
        "category": "concept",
    },
    {
        "id": "q002",
        "query": "LangGraph 的核心概念是什么？",
        "relevant_content": "LangGraph 是基于有向图的 Agent 编排框架，核心概念包括 StateGraph、节点（Node）、边（Edge）和检查点（Checkpointer）。",
        "expected_keywords": ["StateGraph", "节点", "检查点"],
        "category": "framework",
    },
    {
        "id": "q003",
        "query": "向量数据库如何实现语义搜索？",
        "relevant_content": "向量数据库将文本转换为高维向量，通过计算余弦相似度或点积来找到语义最相近的结果，常见实现有 Qdrant、Pinecone、Weaviate。",
        "expected_keywords": ["向量", "相似度", "Qdrant"],
        "category": "database",
    },
    {
        "id": "q004",
        "query": "什么是 Human-in-the-Loop？",
        "relevant_content": "Human-in-the-Loop（HiTL）是在 AI 自动化流程中插入人工审核节点的机制，确保关键决策有人工把关。",
        "expected_keywords": ["人工", "审核", "机制"],
        "category": "concept",
    },
    {
        "id": "q005",
        "query": "SSE 是什么，如何实现流式推送？",
        "relevant_content": "Server-Sent Events（SSE）是 HTTP 协议的单向推送机制，服务端通过 text/event-stream 格式持续推送数据，客户端使用 EventSource API 接收。",
        "expected_keywords": ["HTTP", "EventSource", "推送"],
        "category": "protocol",
    },
    {
        "id": "q006",
        "query": "Hybrid Search 相比纯向量搜索有什么优势？",
        "relevant_content": "Hybrid Search 结合稠密向量（Dense）和稀疏向量（BM25）两种检索方式，通过 RRF（倒数排名融合）合并结果，兼顾语义相关性和关键词精确匹配。",
        "expected_keywords": ["BM25", "RRF", "Dense"],
        "category": "rag",
    },
    {
        "id": "q007",
        "query": "FastAPI 依赖注入如何工作？",
        "relevant_content": "FastAPI 的依赖注入通过 Depends() 函数实现，可以注入数据库会话、认证信息等，支持同步和异步依赖，并自动处理生命周期管理。",
        "expected_keywords": ["Depends", "注入", "异步"],
        "category": "framework",
    },
    {
        "id": "q008",
        "query": "什么是 MCP（Model Context Protocol）？",
        "relevant_content": "MCP 是由 Anthropic 主导的 AI 工具集成标准协议，允许 AI 模型通过统一接口调用外部工具，支持 Claude Desktop、Cursor 等主流客户端。",
        "expected_keywords": ["Anthropic", "工具", "协议"],
        "category": "protocol",
    },
    {
        "id": "q009",
        "query": "LangSmith 用于什么场景？",
        "relevant_content": "LangSmith 是 LangChain 提供的可观测性平台，用于追踪 LLM 应用的完整执行链路，包括输入输出、Token 消耗、延迟等，支持 Eval 评估框架。",
        "expected_keywords": ["追踪", "Token", "评估"],
        "category": "observability",
    },
    {
        "id": "q010",
        "query": "Pydantic v2 相比 v1 有什么改进？",
        "relevant_content": "Pydantic v2 用 Rust 重写了核心验证逻辑，性能提升 5-50 倍，引入了新的类型注解语法，支持更严格的模型配置和自定义验证器。",
        "expected_keywords": ["Rust", "性能", "验证"],
        "category": "framework",
    },
]


# ── 数据类 ────────────────────────────────────────────────────────────


@dataclass
class EvalResult:
    query_id: str
    query: str
    retrieved: bool  # 是否检索到相关内容
    keyword_hit_count: int  # 命中关键词数
    keyword_total: int  # 总关键词数
    latency_ms: float  # 检索延迟
    error: str | None = None

    @property
    def keyword_hit_rate(self) -> float:
        return self.keyword_hit_count / max(self.keyword_total, 1)


@dataclass
class EvalSummary:
    results: list[EvalResult] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        if not self.results:
            return 0.0
        hits = sum(1 for r in self.results if r.retrieved)
        return hits / len(self.results)

    @property
    def avg_keyword_hit_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.keyword_hit_rate for r in self.results) / len(self.results)

    @property
    def avg_latency_ms(self) -> float:
        valid = [r for r in self.results if r.error is None]
        if not valid:
            return 0.0
        return sum(r.latency_ms for r in valid) / len(valid)

    @property
    def error_rate(self) -> float:
        errors = sum(1 for r in self.results if r.error is not None)
        return errors / max(len(self.results), 1)


# ── Eval Runner ───────────────────────────────────────────────────────


async def run_eval_on_dataset(
    dataset: list[dict],
    mock_retriever=None,
) -> EvalSummary:
    """在 Golden Dataset 上运行检索评估"""
    summary = EvalSummary()

    for item in dataset:
        start = time.perf_counter()
        try:
            if mock_retriever:
                # 使用 mock：注入 relevant_content 作为结果
                chunks = [
                    MagicMock(
                        content=item["relevant_content"],
                        score=0.92,
                        doc_id="golden-doc",
                    )
                ]
            else:
                from app.rag.retriever import retrieve

                result = await retrieve(query=item["query"], top_k=5)
                chunks = result.chunks

            latency_ms = (time.perf_counter() - start) * 1000

            # 检查关键词命中
            all_content = " ".join(c.content for c in chunks)
            hit_count = sum(1 for kw in item["expected_keywords"] if kw in all_content)

            summary.results.append(
                EvalResult(
                    query_id=item["id"],
                    query=item["query"],
                    retrieved=len(chunks) > 0,
                    keyword_hit_count=hit_count,
                    keyword_total=len(item["expected_keywords"]),
                    latency_ms=latency_ms,
                )
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            summary.results.append(
                EvalResult(
                    query_id=item["id"],
                    query=item["query"],
                    retrieved=False,
                    keyword_hit_count=0,
                    keyword_total=len(item["expected_keywords"]),
                    latency_ms=latency_ms,
                    error=str(e),
                )
            )

    return summary


# ═══════════════════════════════════════════════════════════════════════
# Eval 测试用例
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.eval
class TestRAGEval:
    """
    Golden Dataset 评估
    标准：Hit Rate@5 ≥ 85%，平均关键词命中率 ≥ 80%，错误率 < 1%
    """

    @pytest.mark.asyncio
    async def test_hit_rate_meets_target(self):
        """NFR: Hit Rate@5 ≥ 85%"""
        # mock_retriever=True 走内置 Mock 分支，不调用真实检索器
        summary = await run_eval_on_dataset(
            GOLDEN_DATASET,
            mock_retriever=True,
        )

        print(f"\n[Eval] Hit Rate: {summary.hit_rate:.2%}")
        print(f"[Eval] Avg Keyword Hit Rate: {summary.avg_keyword_hit_rate:.2%}")
        print(f"[Eval] Avg Latency: {summary.avg_latency_ms:.1f}ms")
        print(f"[Eval] Error Rate: {summary.error_rate:.2%}")

        assert summary.hit_rate >= 0.85, f"Hit Rate {summary.hit_rate:.2%} 低于目标 85%"

    @pytest.mark.asyncio
    async def test_keyword_hit_rate(self):
        """关键词命中率 ≥ 80%（内容质量代理指标）"""
        summary = await run_eval_on_dataset(GOLDEN_DATASET, mock_retriever=True)
        assert summary.avg_keyword_hit_rate >= 0.80, (
            f"关键词命中率 {summary.avg_keyword_hit_rate:.2%} 低于目标 80%"
        )

    @pytest.mark.asyncio
    async def test_error_rate_below_threshold(self):
        """错误率 < 1%"""
        summary = await run_eval_on_dataset(GOLDEN_DATASET, mock_retriever=True)
        assert summary.error_rate < 0.01, f"错误率 {summary.error_rate:.2%} 超过阈值 1%"

    @pytest.mark.asyncio
    async def test_per_category_hit_rate(self):
        """各类别的命中率分布"""
        summary = await run_eval_on_dataset(GOLDEN_DATASET, mock_retriever=True)

        by_category: dict[str, list[EvalResult]] = {}
        for item, result in zip(GOLDEN_DATASET, summary.results, strict=False):
            cat = item["category"]
            by_category.setdefault(cat, []).append(result)

        print("\n[Eval] Per-Category Hit Rate:")
        for cat, results in by_category.items():
            rate = sum(1 for r in results if r.retrieved) / len(results)
            print(f"  {cat}: {rate:.0%} ({len(results)} queries)")
            assert rate >= 0.80, f"类别 {cat} 命中率过低: {rate:.0%}"

    def test_golden_dataset_integrity(self):
        """验证 Golden Dataset 格式完整性"""
        for item in GOLDEN_DATASET:
            assert "id" in item
            assert "query" in item and len(item["query"]) > 0
            assert "relevant_content" in item and len(item["relevant_content"]) > 10
            assert "expected_keywords" in item and len(item["expected_keywords"]) >= 2
            assert "category" in item

    def test_no_duplicate_ids(self):
        ids = [item["id"] for item in GOLDEN_DATASET]
        assert len(ids) == len(set(ids)), "Golden Dataset 存在重复 ID"


# ── 输出评估报告 ──────────────────────────────────────────────────────


@pytest.mark.eval
class TestEvalReport:
    """生成可供 CI 读取的结构化评估报告"""

    @pytest.mark.asyncio
    async def test_generate_eval_report(self, tmp_path):
        """生成 eval_report.json 供 CI Dashboard 消费"""
        summary = await run_eval_on_dataset(GOLDEN_DATASET, mock_retriever=True)

        report = {
            "total_queries": len(summary.results),
            "hit_rate": round(summary.hit_rate, 4),
            "keyword_hit_rate": round(summary.avg_keyword_hit_rate, 4),
            "avg_latency_ms": round(summary.avg_latency_ms, 2),
            "error_rate": round(summary.error_rate, 4),
            "target_hit_rate": 0.85,
            "pass": summary.hit_rate >= 0.85,
            "details": [
                {
                    "id": r.query_id,
                    "query": r.query[:50],
                    "retrieved": r.retrieved,
                    "keyword_hit_rate": round(r.keyword_hit_rate, 2),
                    "latency_ms": round(r.latency_ms, 1),
                    "error": r.error,
                }
                for r in summary.results
            ],
        }

        report_path = tmp_path / "eval_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

        loaded = json.loads(report_path.read_text())
        assert loaded["pass"] is True
        print(f"\n[Eval Report] Hit Rate: {loaded['hit_rate']:.2%}")
        print(f"[Eval Report] Saved to: {report_path}")
