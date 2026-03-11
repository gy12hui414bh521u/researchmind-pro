"""
单元测试 — API 路由层（修复版 v3）

修复内容：
1. depth → "deep"/"quick"
2. cancel/cancel_nonexistent：patch TaskRepository.cancel（因为 cancel SQL 用了 NOW()，SQLite 不支持）
3. test_kb_search：用真实 ChunkResult 对象（Pydantic 不接受 MagicMock）
4. ingest 系列：patch _run_ingest_* 后台任务函数
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# Health 路由
# ═══════════════════════════════════════════════════════════════════════

class TestHealthRoutes:

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_detail_structure(self, client):
        with (
            patch("app.db.database.check_db_connection", AsyncMock(return_value=True)),
            patch("app.rag.retriever.get_collection_stats",
                  AsyncMock(return_value={"status": "green", "vectors_count": 500})),
            patch("redis.asyncio.from_url") as mock_redis,
        ):
            mock_r = AsyncMock()
            mock_redis.return_value = mock_r
            mock_r.ping = AsyncMock()
            mock_r.aclose = AsyncMock()
            resp = await client.get("/api/v1/health/detail")

        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "components" in data

    @pytest.mark.asyncio
    async def test_health_detail_degraded_when_db_fails(self, client):
        with (
            patch("app.db.database.check_db_connection", AsyncMock(return_value=False)),
            patch("app.rag.retriever.get_collection_stats",
                  AsyncMock(return_value={"status": "green", "vectors_count": 0})),
            patch("redis.asyncio.from_url") as mock_redis,
        ):
            mock_r = AsyncMock()
            mock_redis.return_value = mock_r
            mock_r.ping = AsyncMock()
            mock_r.aclose = AsyncMock()
            resp = await client.get("/api/v1/health/detail")

        assert resp.json()["status"] == "degraded"


# ═══════════════════════════════════════════════════════════════════════
# Tasks 路由
# ═══════════════════════════════════════════════════════════════════════

class TestTaskRoutes:

    @pytest.mark.asyncio
    async def test_create_task_returns_201(self, client, sample_task_create):
        resp = await client.post("/api/v1/tasks", json=sample_task_create)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["query"] == sample_task_create["query"]
        assert data["depth"] == sample_task_create["depth"]

    @pytest.mark.asyncio
    async def test_create_task_depth_validation(self, client):
        """depth 必须是 TaskDepth enum 值：'quick' 或 'deep'"""
        resp = await client.post("/api/v1/tasks", json={
            "query": "测试查询内容足够长才能通过", "depth": "invalid"
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_empty_query_rejected(self, client):
        # query min_length=5
        resp = await client.post("/api/v1/tasks", json={"query": "hi", "depth": "deep"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, client):
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, client):
        for i in range(3):
            await client.post("/api/v1/tasks", json={
                "query": f"研究任务内容 第{i}个任务测试", "depth": "quick"
            })

        resp = await client.get("/api/v1/tasks?page=1&size=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["size"] == 2

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, client):
        fake_id = "00000000-0000-0000-0000-000000000999"
        resp = await client.get(f"/api/v1/tasks/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_detail(self, client, sample_task_create):
        create_resp = await client.post("/api/v1/tasks", json=sample_task_create)
        assert create_resp.status_code == 201
        task_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert "cost" in data
        assert "iteration_count" in data

    @pytest.mark.asyncio
    async def test_cancel_task(self, client, sample_task_create):
        create_resp = await client.post("/api/v1/tasks", json=sample_task_create)
        assert create_resp.status_code == 201
        task_id = create_resp.json()["id"]

        # cancel() SQL 用了 NOW()（PostgreSQL 函数），SQLite 不支持，patch 掉
        with patch("app.db.repositories.TaskRepository.cancel",
                   AsyncMock(return_value=True)):
            resp = await client.delete(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, client):
        fake_id = "00000000-0000-0000-0000-000000000999"
        # cancel() 返回 False/None 表示未找到，路由应返回 400
        with patch("app.db.repositories.TaskRepository.cancel",
                   AsyncMock(return_value=False)):
            resp = await client.delete(f"/api/v1/tasks/{fake_id}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_task_without_hitl_flag(self, client, sample_task_create):
        create_resp = await client.post("/api/v1/tasks", json=sample_task_create)
        assert create_resp.status_code == 201
        task_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "approve", "comment": "LGTM"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Knowledge 路由
# ═══════════════════════════════════════════════════════════════════════

class TestKnowledgeRoutes:

    @pytest.mark.asyncio
    async def test_ingest_text_returns_202(self, client, sample_doc_text):
        with patch("app.api.knowledge._run_ingest_text", AsyncMock()):
            resp = await client.post("/api/v1/kb/ingest/text", json={
                "text": sample_doc_text,
                "title": "测试文档",
            })
        assert resp.status_code == 202
        data = resp.json()
        assert "doc_id" in data
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_ingest_url_returns_202(self, client):
        with patch("app.api.knowledge._run_ingest_url", AsyncMock()):
            resp = await client.post("/api/v1/kb/ingest/url", json={
                "url": "https://example.com/ai-report",
                "title": "AI 市场报告",
            })
        assert resp.status_code == 202
        assert resp.json()["status"] == "processing"

    @pytest.mark.asyncio
    async def test_ingest_file_pdf(self, client):
        pdf_bytes = b"%PDF-1.4 fake pdf content for testing"
        with patch("app.api.knowledge._run_ingest_file", AsyncMock()):
            resp = await client.post(
                "/api/v1/kb/ingest/file",
                files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
                data={"title": "PDF测试"},
            )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_ingest_file_unsupported_type(self, client):
        resp = await client.post(
            "/api/v1/kb/ingest/file",
            files={"file": ("data.xlsx", b"fake", "application/vnd.ms-excel")},
        )
        assert resp.status_code == 415

    @pytest.mark.asyncio
    async def test_list_documents_empty(self, client):
        resp = await client.get("/api/v1/kb/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, client):
        resp = await client.delete("/api/v1/kb/documents/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_kb_search(self, client):
        from app.models.document import ChunkResult
        mock_chunk = ChunkResult(
            chunk_id="chunk-1",
            text="大模型市场分析内容详细说明",
            score=0.91,
            doc_id="doc-1",
            title="AI报告",
            source_url=None,
            source_type="internal",
        )
        with patch("app.rag.retriever.retrieve", AsyncMock(return_value=MagicMock(
            chunks=[mock_chunk],
            total_found=1,
        ))):
            resp = await client.post("/api/v1/kb/search", json={
                "query": "大模型市场",
                "top_k": 5,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_kb_stats(self, client):
        with patch("app.rag.retriever.get_collection_stats", AsyncMock(return_value={
            "vectors_count": 1200,
            "status": "green",
        })):
            resp = await client.get("/api/v1/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_documents" in data
        assert "vectors_count" in data
        assert "qdrant_status" in data