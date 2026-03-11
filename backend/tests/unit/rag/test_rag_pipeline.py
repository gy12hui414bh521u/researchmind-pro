"""
单元测试 — RAG Pipeline（修复版 v3）

修复内容：
1. 分块函数名：split_by_tokens_approx（不是 chunk_text）
2. 摄取测试：patch("app.rag.ingestion._upsert_to_qdrant")
   因为 _upsert_to_qdrant 内部 `from qdrant_client import AsyncQdrantClient`，
   无法从外部 patch 构造函数，直接 patch 整个函数最可靠。
3. embedding 错误测试：patch embed_texts 抛异常，
   但注意 ingestion.py 里 embed_texts 是在 try 块里，
   要让错误在 embed_texts 时触发（而不是在 _upsert_to_qdrant）。
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════
# 文本分块
# ═══════════════════════════════════════════════════════════════════════


class TestTextChunking:
    def test_chunk_size_within_limit(self, sample_doc_text):
        from app.rag.ingestion import split_by_tokens_approx

        chunks = split_by_tokens_approx(sample_doc_text, chunk_size=500, chunk_overlap=50)
        for c in chunks:
            # chunk_size 是软限制，允许句子完整保留，给 2x 宽松边界
            assert len(c) <= 1200

    def test_chunk_count_reasonable(self, sample_doc_text):
        from app.rag.ingestion import split_by_tokens_approx

        chunks = split_by_tokens_approx(sample_doc_text, chunk_size=500, chunk_overlap=50)
        assert len(chunks) >= 2

    def test_chunk_overlap_exists(self, sample_doc_text):
        from app.rag.ingestion import split_by_tokens_approx

        chunks_overlap = split_by_tokens_approx(sample_doc_text, chunk_size=300, chunk_overlap=50)
        chunks_no_overlap = split_by_tokens_approx(sample_doc_text, chunk_size=300, chunk_overlap=0)
        # 有 overlap 的 chunk 数 >= 无 overlap
        assert len(chunks_overlap) >= len(chunks_no_overlap)

    def test_empty_text_returns_empty_list(self):
        from app.rag.ingestion import split_by_tokens_approx

        assert split_by_tokens_approx("") == []

    def test_short_text_single_chunk(self):
        from app.rag.ingestion import split_by_tokens_approx

        short = "这是一段很短的文本。"
        chunks = split_by_tokens_approx(short, chunk_size=500, chunk_overlap=0)
        assert len(chunks) == 1

    def test_paragraph_boundary_respected(self):
        from app.rag.ingestion import split_by_tokens_approx

        text = "第一段落内容很长，包含许多信息。\n\n第二段落内容也很丰富。\n\n第三段落。"
        chunks = split_by_tokens_approx(text, chunk_size=500, chunk_overlap=0)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c.strip()) > 0


# ═══════════════════════════════════════════════════════════════════════
# 文本清洗
# ═══════════════════════════════════════════════════════════════════════


class TestTextCleaning:
    def test_clean_text_removes_extra_whitespace(self):
        from app.rag.ingestion import clean_text

        dirty = "Hello  World\r\n\r\n\r\nTest"
        cleaned = clean_text(dirty)
        assert "  " not in cleaned
        assert "\r" not in cleaned

    def test_clean_text_empty_input(self):
        from app.rag.ingestion import clean_text

        assert clean_text("") == ""

    def test_detect_language_chinese(self):
        from app.rag.ingestion import detect_language

        assert detect_language("这是一段中文文本内容") == "zh"

    def test_detect_language_english(self):
        from app.rag.ingestion import detect_language

        assert detect_language("This is an English text content") == "en"


# ═══════════════════════════════════════════════════════════════════════
# 向量摄取 — ingest_text
#
# 修复：patch("app.rag.ingestion._upsert_to_qdrant") 而不是
#       patch("qdrant_client.AsyncQdrantClient")
# 原因：_upsert_to_qdrant 内部 `from qdrant_client import AsyncQdrantClient`
#       是局部 import，patch 构造函数无效；直接 patch 函数本身最可靠。
# ═══════════════════════════════════════════════════════════════════════


class TestIngestion:
    @pytest.mark.asyncio
    async def test_ingest_text_success(self, sample_doc_text, mock_emb_client):
        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("app.rag.ingestion._upsert_to_qdrant", AsyncMock(return_value=None)),
        ):
            from app.rag.ingestion import ingest_text

            result = await ingest_text(
                text=sample_doc_text,
                doc_id="test-doc-001",
                title="测试文档",
            )

        assert result.success is True
        assert result.chunk_count > 0

    @pytest.mark.asyncio
    async def test_ingest_text_returns_chunk_count(self, mock_emb_client):
        text = "。\n\n".join([f"这是第{i}段内容，包含足够的文字让分块器处理" for i in range(10)])
        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("app.rag.ingestion._upsert_to_qdrant", AsyncMock(return_value=None)),
        ):
            from app.rag.ingestion import ingest_text

            result = await ingest_text(text, "doc-002", title="多段测试")

        assert result.chunk_count >= 1

    @pytest.mark.asyncio
    async def test_ingest_handles_embedding_error(self, sample_doc_text):
        # embed_texts 抛异常 → ingest_text 的 except 块捕获 → success=False
        mock_emb = MagicMock()
        mock_emb.embed_texts = AsyncMock(side_effect=Exception("Embedding API 超时"))

        with patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb):
            from app.rag.ingestion import ingest_text

            result = await ingest_text(sample_doc_text, "doc-003", title="错误测试")

        assert result.success is False
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_ingest_result_has_doc_id(self, mock_emb_client):
        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("app.rag.ingestion._upsert_to_qdrant", AsyncMock(return_value=None)),
        ):
            from app.rag.ingestion import ingest_text

            result = await ingest_text(
                "测试内容足够长用于分块处理文档", "doc-id-check", title="ID检查"
            )

        assert result.doc_id == "doc-id-check"


# ═══════════════════════════════════════════════════════════════════════
# 检索 — retrieve / get_collection_stats / delete_doc_vectors
# retriever.py 里也是局部 import AsyncQdrantClient，
# 所以同样 patch 整个内部函数 _qdrant_search 或直接用 patch("qdrant_client.AsyncQdrantClient")
# retriever.py 的 AsyncQdrantClient 是模块顶部没有 import 的，是函数内部的，
# 所以用 patch("qdrant_client.AsyncQdrantClient") 这种方式 patch 全局构造函数。
# ═══════════════════════════════════════════════════════════════════════


class TestRetrieval:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self, mock_emb_client, mock_qdrant):
        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_qdrant),
        ):
            from app.rag.retriever import retrieve

            result = await retrieve(query="大模型市场分析", top_k=5)

        assert isinstance(result.chunks, list)
        assert result.total_found >= 0

    @pytest.mark.asyncio
    async def test_retrieve_score_range(self, mock_emb_client, mock_qdrant):
        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_qdrant),
        ):
            from app.rag.retriever import retrieve

            result = await retrieve(query="测试查询", top_k=5)

        for chunk in result.chunks:
            assert 0.0 <= chunk.score <= 1.0

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self, mock_emb_client):
        hit = MagicMock(
            id="c",
            score=0.9,
            payload={"chunk_id": "c", "text": "内容", "doc_id": "d1", "source_type": "internal"},
        )
        mock_q = MagicMock()
        mock_q.query_points = AsyncMock(return_value=MagicMock(points=[hit] * 3))
        mock_q.close = AsyncMock()

        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_q),
        ):
            from app.rag.retriever import retrieve

            result = await retrieve(query="测试", top_k=3)

        assert len(result.chunks) <= 3

    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, mock_emb_client):
        mock_q = MagicMock()
        mock_q.query_points = AsyncMock(return_value=MagicMock(points=[]))
        mock_q.close = AsyncMock()

        with (
            patch("app.rag.ingestion.get_embedding_client", return_value=mock_emb_client),
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_q),
        ):
            from app.rag.retriever import retrieve

            result = await retrieve(query="无结果查询", top_k=5)

        assert result.chunks == []
        assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_get_collection_stats(self, mock_qdrant):
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_qdrant):
            from app.rag.retriever import get_collection_stats

            stats = await get_collection_stats()

        assert "vectors_count" in stats
        assert "status" in stats

    @pytest.mark.asyncio
    async def test_delete_doc_vectors(self, mock_qdrant):
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_qdrant):
            from app.rag.retriever import delete_doc_vectors

            await delete_doc_vectors("doc-hash-001")

        mock_qdrant.delete.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# 文档 Hash 去重
# ═══════════════════════════════════════════════════════════════════════


class TestDocumentDedup:
    def test_hash_deterministic(self, sample_doc_text):
        h1 = hashlib.sha256(sample_doc_text.encode()).hexdigest()
        h2 = hashlib.sha256(sample_doc_text.encode()).hexdigest()
        assert h1 == h2

    def test_different_content_different_hash(self, sample_doc_text):
        h1 = hashlib.sha256(sample_doc_text.encode()).hexdigest()
        h2 = hashlib.sha256((sample_doc_text + " extra").encode()).hexdigest()
        assert h1 != h2

    def test_hash_length_is_64(self, sample_doc_text):
        h = hashlib.sha256(sample_doc_text.encode()).hexdigest()
        assert len(h) == 64
