"""
知识库路由

POST   /api/v1/kb/ingest/file    — 上传文件（PDF/Markdown/TXT）
POST   /api/v1/kb/ingest/url     — 摄取网页 URL
POST   /api/v1/kb/ingest/text    — 摄取纯文本
GET    /api/v1/kb/documents      — 文档列表
DELETE /api/v1/kb/documents/{id} — 删除文档
POST   /api/v1/kb/search         — 语义搜索预览
GET    /api/v1/kb/stats          — 集合统计
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_doc_repo
from app.db.repositories import DocumentRepository
from app.models.document import (
    DocumentIngestResponse, DocumentIngestText, DocumentIngestURL,
    DocumentListResponse, DocumentResponse, DocumentSourceType,
    DocumentStatus, SearchRequest, SearchResponse,
)

router = APIRouter()

# 允许的文件类型
ALLOWED_TYPES = {
    "application/pdf":  DocumentSourceType.PDF,
    "text/markdown":    DocumentSourceType.MARKDOWN,
    "text/plain":       DocumentSourceType.TEXT,
    "text/x-markdown":  DocumentSourceType.MARKDOWN,
}


# ── POST /ingest/file  上传文件 ───────────────────────────────────────

@router.post("/ingest/file", response_model=DocumentIngestResponse, status_code=202)
async def ingest_file(
    file:     UploadFile          = File(...),
    title:    str | None          = Form(default=None),
    doc_repo: DocumentRepository  = Depends(get_doc_repo),
):
    """上传 PDF / Markdown / TXT 文件到知识库"""
    content_type = file.content_type or ""

    # 按扩展名推断
    if content_type not in ALLOWED_TYPES:
        name = (file.filename or "").lower()
        if name.endswith(".pdf"):
            content_type = "application/pdf"
        elif name.endswith((".md", ".markdown")):
            content_type = "text/markdown"
        elif name.endswith(".txt"):
            content_type = "text/plain"
        else:
            raise HTTPException(
                status_code=415,
                detail=f"不支持的文件类型: {content_type}，支持 PDF/Markdown/TXT"
            )

    source_type = ALLOWED_TYPES[content_type]
    file_bytes  = await file.read()
    doc_title   = title or file.filename or "未命名文档"

    # 幂等检查：同内容不重复摄取
    import hashlib
    doc_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = await doc_repo.find_by_hash(doc_hash)
    if existing and existing["status"] == "completed":
        return DocumentIngestResponse(
            doc_id=      existing["id"],
            status=      DocumentStatus.COMPLETED,
            chunk_count= existing["chunk_count"],
            message=     "文档已存在，跳过重复摄取",
        )

    # 创建文档记录
    from app.config import settings
    row = await doc_repo.create(
        doc_hash=       doc_hash,
        title=          doc_title,
        source_type=    source_type,
        source_url=     None,
        file_name=      file.filename,
        embedding_model=settings.qwen_embedding_model,
    )
    doc_id = str(row["id"])

    # 异步摄取（不阻塞响应）
    import asyncio
    asyncio.create_task(_run_ingest_file(doc_id, file_bytes, doc_title, source_type, doc_repo))

    return DocumentIngestResponse(
        doc_id=  doc_id,
        status=  DocumentStatus.PROCESSING,
        message= "摄取任务已提交，请稍后查询状态",
    )


# ── POST /ingest/url  摄取网页 ────────────────────────────────────────

@router.post("/ingest/url", response_model=DocumentIngestResponse, status_code=202)
async def ingest_url(
    body:     DocumentIngestURL,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """摄取网页内容到知识库"""
    from app.config import settings

    doc_id = str(uuid.uuid4())
    row = await doc_repo.create(
        doc_hash=       f"url_{uuid.uuid4().hex}",   # URL 内容动态，用随机 hash
        title=          body.title or body.url,
        source_type=    DocumentSourceType.URL,
        source_url=     body.url,
        file_name=      None,
        embedding_model=settings.qwen_embedding_model,
        metadata=       body.metadata,
    )
    doc_id = str(row["id"])

    import asyncio
    asyncio.create_task(_run_ingest_url(doc_id, body.url, doc_repo))

    return DocumentIngestResponse(
        doc_id=  doc_id,
        status=  DocumentStatus.PROCESSING,
        message= "URL 摄取任务已提交",
    )


# ── POST /ingest/text  摄取纯文本 ────────────────────────────────────

@router.post("/ingest/text", response_model=DocumentIngestResponse, status_code=202)
async def ingest_text_endpoint(
    body:     DocumentIngestText,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    """直接摄取纯文本内容"""
    import hashlib
    from app.config import settings

    doc_hash = hashlib.sha256(body.text.encode()).hexdigest()
    existing = await doc_repo.find_by_hash(doc_hash)
    if existing and existing["status"] == "completed":
        return DocumentIngestResponse(
            doc_id=      existing["id"],
            status=      DocumentStatus.COMPLETED,
            chunk_count= existing["chunk_count"],
            message=     "内容已存在，跳过重复摄取",
        )

    row = await doc_repo.create(
        doc_hash=       doc_hash,
        title=          body.title,
        source_type=    DocumentSourceType.TEXT,
        source_url=     None,
        file_name=      None,
        embedding_model=settings.qwen_embedding_model,
        metadata=       body.metadata,
    )
    doc_id = str(row["id"])

    import asyncio
    asyncio.create_task(_run_ingest_text(doc_id, body.text, body.title, doc_repo))

    return DocumentIngestResponse(
        doc_id=  doc_id,
        status=  DocumentStatus.PROCESSING,
        message= "文本摄取任务已提交",
    )


# ── GET /documents  文档列表 ──────────────────────────────────────────

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    page:     int                = 1,
    size:     int                = 20,
    status:   str | None         = None,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    items, total = await doc_repo.list_all(page, size, status)
    return DocumentListResponse(
        items=[_row_to_doc(r) for r in items],
        total=total, page=page, size=size,
    )


# ── DELETE /documents/{id}  删除文档 ─────────────────────────────────

@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id:   str,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
):
    row = await doc_repo.get(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 从 Qdrant 删除向量
    from app.rag.retriever import delete_doc_vectors
    await delete_doc_vectors(row["doc_hash"])

    # 从 PostgreSQL 删除记录
    await doc_repo.delete(doc_id)


# ── POST /search  语义搜索 ────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search_knowledge(body: SearchRequest):
    """知识库语义搜索（用于前端预览，不记录到任务）"""
    from app.rag.retriever import retrieve

    result = await retrieve(query=body.query, top_k=body.top_k, filters=body.filters)
    return SearchResponse(
        query=   body.query,
        results= result.chunks,
        total=   result.total_found,
    )


# ── GET /stats  统计信息 ──────────────────────────────────────────────

@router.get("/stats")
async def kb_stats(doc_repo: DocumentRepository = Depends(get_doc_repo)):
    from app.rag.retriever import get_collection_stats

    qdrant_stats = await get_collection_stats()
    items, total = await doc_repo.list_all(page=1, size=1)

    return {
        "total_documents": total,
        "vectors_count":   qdrant_stats.get("vectors_count", 0),
        "qdrant_status":   qdrant_stats.get("status", "unknown"),
    }


# ── 后台摄取任务 ──────────────────────────────────────────────────────

async def _run_ingest_file(
    doc_id: str, file_bytes: bytes, title: str,
    source_type: DocumentSourceType, doc_repo: DocumentRepository,
):
    try:
        from app.rag.ingestion import ingest_pdf, ingest_text

        if source_type == DocumentSourceType.PDF:
            result = await ingest_pdf(file_bytes, doc_id, title)
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            result = await ingest_text(text, doc_id, title=title,
                                       source_type=source_type.value)

        if result.success:
            await doc_repo.update_completed(doc_id, result.chunk_count)
        else:
            await doc_repo.update_failed(doc_id, result.error)
    except Exception as e:
        await doc_repo.update_failed(doc_id, str(e))


async def _run_ingest_url(doc_id: str, url: str, doc_repo: DocumentRepository):
    try:
        from app.rag.ingestion import ingest_url
        result = await ingest_url(url, doc_id)
        if result.success:
            await doc_repo.update_completed(doc_id, result.chunk_count)
        else:
            await doc_repo.update_failed(doc_id, result.error)
    except Exception as e:
        await doc_repo.update_failed(doc_id, str(e))


async def _run_ingest_text(doc_id: str, text: str, title: str, doc_repo: DocumentRepository):
    try:
        from app.rag.ingestion import ingest_text
        result = await ingest_text(text, doc_id, title=title)
        if result.success:
            await doc_repo.update_completed(doc_id, result.chunk_count)
        else:
            await doc_repo.update_failed(doc_id, result.error)
    except Exception as e:
        await doc_repo.update_failed(doc_id, str(e))


# ── 工具函数 ──────────────────────────────────────────────────────────

def _row_to_doc(row: dict) -> DocumentResponse:
    return DocumentResponse(
        id=              row["id"],
        title=           row.get("title"),
        source_type=     DocumentSourceType(row["source_type"]),
        source_url=      row.get("source_url"),
        file_name=       row.get("file_name"),
        chunk_count=     row.get("chunk_count", 0),
        embedding_model= row.get("embedding_model", ""),
        status=          DocumentStatus(row["status"]),
        metadata=        row.get("metadata") or {},
        created_at=      row["created_at"],
        updated_at=      row["updated_at"],
        error_message=   row.get("error_message"),
    )
