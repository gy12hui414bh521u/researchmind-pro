"""
单元测试 — Pydantic 数据模型（修复版 v3）

修复内容：
1. TaskCreate.depth → TaskDepth enum："quick"/"deep"
2. DocumentIngestText.text min_length=10，测试用例字符数必须 >= 10
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestTaskModels:
    def test_task_create_valid_deep(self):
        from app.models.task import TaskCreate, TaskDepth

        t = TaskCreate(query="分析AI市场竞争格局趋势", depth=TaskDepth.DEEP)
        assert t.depth == TaskDepth.DEEP

    def test_task_create_valid_quick(self):
        from app.models.task import TaskCreate, TaskDepth

        t = TaskCreate(query="快速查询分析任务内容", depth="quick")
        assert t.depth == TaskDepth.QUICK

    def test_task_create_default_depth_is_deep(self):
        from app.models.task import TaskCreate, TaskDepth

        t = TaskCreate(query="默认深度测试任务内容")
        assert t.depth == TaskDepth.DEEP

    def test_task_create_query_required(self):
        from app.models.task import TaskCreate

        with pytest.raises(ValidationError):
            TaskCreate(depth="deep")

    def test_task_create_invalid_depth(self):
        from app.models.task import TaskCreate

        with pytest.raises(ValidationError):
            TaskCreate(query="测试查询内容足够长", depth="medium")

    def test_task_create_query_too_short(self):
        from app.models.task import TaskCreate

        with pytest.raises(ValidationError):
            # min_length=5
            TaskCreate(query="hi", depth="deep")

    def test_task_create_query_too_long(self):
        from app.models.task import TaskCreate

        with pytest.raises(ValidationError):
            # max_length=2000
            TaskCreate(query="x" * 2001, depth="deep")

    def test_task_approve_valid_actions(self):
        from app.models.task import TaskApprove

        for action in ("approve", "modify", "reject"):
            t = TaskApprove(action=action)
            assert t.action == action

    def test_task_approve_invalid_action(self):
        from app.models.task import TaskApprove

        with pytest.raises(ValidationError):
            TaskApprove(action="delete")

    def test_task_status_enum_values(self):
        from app.models.task import TaskStatus

        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_task_depth_enum_values(self):
        from app.models.task import TaskDepth

        assert TaskDepth.QUICK == "quick"
        assert TaskDepth.DEEP == "deep"


class TestDocumentModels:
    def test_ingest_url_requires_valid_url(self):
        from app.models.document import DocumentIngestURL

        with pytest.raises(ValidationError):
            DocumentIngestURL(url="not-a-url")

    def test_ingest_url_valid(self):
        from app.models.document import DocumentIngestURL

        d = DocumentIngestURL(url="https://example.com/report")
        assert str(d.url).startswith("https://")

    def test_ingest_text_requires_title(self):
        from app.models.document import DocumentIngestText

        with pytest.raises(ValidationError):
            # title is required
            DocumentIngestText(text="足够长的测试内容文本")

    def test_ingest_text_valid(self):
        from app.models.document import DocumentIngestText

        # text min_length=10，需要至少10个字符
        d = DocumentIngestText(text="这是测试内容文本足够长", title="测试标题")
        assert d.title == "测试标题"

    def test_ingest_text_too_short(self):
        from app.models.document import DocumentIngestText

        with pytest.raises(ValidationError):
            # "测试内容" = 4 chars < 10
            DocumentIngestText(text="测试内容", title="标题")

    def test_document_status_enum(self):
        from app.models.document import DocumentStatus

        assert DocumentStatus.PROCESSING == "processing"
        assert DocumentStatus.COMPLETED == "completed"
        assert DocumentStatus.FAILED == "failed"

    def test_search_request_default_top_k(self):
        from app.models.document import SearchRequest

        r = SearchRequest(query="test")
        assert r.top_k == 5

    def test_search_request_custom_top_k(self):
        from app.models.document import SearchRequest

        r = SearchRequest(query="test", top_k=10)
        assert r.top_k == 10

    def test_chunk_result_model(self):
        from app.models.document import ChunkResult

        c = ChunkResult(
            chunk_id="c-001",
            text="测试内容文本",
            score=0.92,
            doc_id="doc-001",
        )
        assert c.chunk_id == "c-001"
        assert c.score == 0.92
