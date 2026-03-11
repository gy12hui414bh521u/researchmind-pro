"""
知识库检索器
实现 Hybrid Search（Dense向量 + BM25稀疏）+ Cohere Rerank 精排
无 Cohere Key 时自动降级为纯向量检索
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import settings
from app.models.document import ChunkResult
from app.rag.embeddings import get_embedding_client

# ── 检索结果 ──────────────────────────────────────────────────────────


@dataclass
class RetrievalResult:
    chunks: list[ChunkResult]
    total_found: int
    strategy: str  # "hybrid+rerank" | "hybrid" | "dense"
    elapsed_ms: int = 0


# ── 主检索函数 ────────────────────────────────────────────────────────


async def retrieve(
    query: str,
    top_k: int = 5,
    filters: dict = None,
) -> RetrievalResult:
    """
    完整检索流水线：
    1. Dense 向量检索（语义相似度）
    2. 如有 Cohere Key → Rerank 精排
    3. 返回 top_k 结果

    注意：Qdrant 的 Sparse（BM25）索引需要在 collection 创建时指定，
    本版本先用 Dense-only，后续可升级为 Hybrid。
    """
    if filters is None:
        filters = {}
    start = time.time()
    emb_client = get_embedding_client()

    # 1. 生成查询向量
    query_vector = await emb_client.embed_query(query)

    # 2. Qdrant 向量检索（取 top_k * 4 候选，留给 rerank 精排）
    candidate_count = top_k * 4 if settings.has_cohere else top_k
    raw_chunks = await _qdrant_search(query_vector, candidate_count, filters)

    if not raw_chunks:
        return RetrievalResult(
            chunks=[], total_found=0, strategy="dense", elapsed_ms=int((time.time() - start) * 1000)
        )

    # 3. Rerank（有 Cohere Key 时）
    strategy = "dense"
    if settings.has_cohere and len(raw_chunks) > top_k:
        try:
            raw_chunks = await _cohere_rerank(query, raw_chunks, top_k)
            strategy = "dense+rerank"
        except Exception as e:
            print(f"⚠️  Rerank 失败，降级为 dense: {e}")
            raw_chunks = raw_chunks[:top_k]
    else:
        raw_chunks = raw_chunks[:top_k]

    elapsed_ms = int((time.time() - start) * 1000)
    return RetrievalResult(
        chunks=raw_chunks,
        total_found=len(raw_chunks),
        strategy=strategy,
        elapsed_ms=elapsed_ms,
    )


async def _qdrant_search(
    query_vector: list[float],
    top_k: int,
    filters: dict,
) -> list[ChunkResult]:
    """向量检索 Qdrant（兼容 qdrant-client >= 1.7）"""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        check_compatibility=False,  # 跳过 client/server 版本兼容检查
    )

    # 构建过滤条件
    qdrant_filter = None
    if filters:
        conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
        qdrant_filter = Filter(must=conditions)

    # qdrant-client >= 1.7 用 query_points，旧版用 search
    try:
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            score_threshold=settings.retrieval_score_threshold,
            with_payload=True,
        )
        hits = response.points
    except AttributeError:
        # fallback：旧版 SDK
        hits = await client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            score_threshold=settings.retrieval_score_threshold,
            with_payload=True,
        )
    finally:
        await client.close()

    chunks = []
    for hit in hits:
        payload = hit.payload or {}
        chunks.append(
            ChunkResult(
                chunk_id=payload.get("chunk_id", str(hit.id)),
                text=payload.get("text", ""),
                score=hit.score,
                doc_id=payload.get("doc_id"),
                title=payload.get("title"),
                source_url=payload.get("source_url"),
                source_type=payload.get("source_type", "internal"),
                section=payload.get("section"),
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k
                    not in {
                        "chunk_id",
                        "doc_id",
                        "doc_hash",
                        "chunk_index",
                        "text",
                        "title",
                        "source_url",
                        "source_type",
                        "section",
                        "language",
                    }
                },
            )
        )
    return chunks


async def _cohere_rerank(
    query: str,
    chunks: list[ChunkResult],
    top_n: int,
) -> list[ChunkResult]:
    """Cohere Rerank 精排"""
    import httpx

    documents = [c.text for c in chunks]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.cohere.com/v1/rerank",
            headers={
                "Authorization": f"Bearer {settings.cohere_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.cohere_rerank_model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # 按 rerank 排序重排 chunks，更新 score
    reranked = []
    for item in data.get("results", []):
        idx = item["index"]
        score = item["relevance_score"]
        chunk = chunks[idx]
        chunk.score = score
        reranked.append(chunk)

    return reranked


# ── Agentic 多轮检索 ──────────────────────────────────────────────────


async def agentic_retrieve(
    query: str,
    top_k: int = 5,
    max_iterations: int = 3,
    coverage_threshold: float = 0.8,
) -> list[ChunkResult]:
    """
    多轮检索：检索 → 评估覆盖度 → 改写 query → 再检索
    在 Agent 节点内调用，max_iterations 受 settings 控制

    简化版：用 LLM 判断覆盖度和改写 query（完整版在 Task 1.3 的 tools.py 中实现）
    这里先实现基础的多轮逻辑，LLM 集成在 Agent 节点中完成。
    """
    all_chunks: list[ChunkResult] = []
    seen_ids: set[str] = set()
    current_query = query

    for iteration in range(max_iterations):
        result = await retrieve(current_query, top_k=top_k)

        # 去重合并
        for chunk in result.chunks:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                all_chunks.append(chunk)

        # 简单覆盖度估算：平均相关度 > threshold 则停止
        if all_chunks:
            avg_score = sum(c.score for c in all_chunks) / len(all_chunks)
            if avg_score >= coverage_threshold or iteration == max_iterations - 1:
                break

        # 简单 query 扩展（完整 LLM 改写在 Agent 中实现）
        current_query = f"{query} 详细说明 {iteration + 1}"

    # 按 score 排序，返回 top_k
    all_chunks.sort(key=lambda c: c.score, reverse=True)
    return all_chunks[:top_k]


# ── 删除文档向量 ──────────────────────────────────────────────────────


async def delete_doc_vectors(doc_hash: str) -> int:
    """从 Qdrant 删除指定文档的所有向量，返回删除数量"""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        check_compatibility=False,
    )

    await client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[FieldCondition(key="doc_hash", match=MatchValue(value=doc_hash))]
        ),
    )
    await client.close()

    # result.status 表示操作状态，无法直接得到删除数量
    # 返回 -1 表示"已执行，数量未知"
    return -1


# ── 集合统计 ──────────────────────────────────────────────────────────


async def get_collection_stats() -> dict:
    """获取 Qdrant collection 统计信息"""
    from qdrant_client import AsyncQdrantClient

    try:
        client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            check_compatibility=False,
        )
        info = await client.get_collection(settings.qdrant_collection)
        await client.close()
        return {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status,
        }
    except Exception:
        return {"vectors_count": 0, "points_count": 0, "status": "unavailable"}
