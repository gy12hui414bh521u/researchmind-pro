"""
知识库文档（Document）相关 Pydantic 模型
涵盖：摄取请求/响应、检索结果、文档列表
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ── 枚举 ──────────────────────────────────────────────────────────────


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentSourceType(StrEnum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    URL = "url"
    TEXT = "text"
    MANUAL = "manual"


# ── 摄取请求 ──────────────────────────────────────────────────────────


class DocumentIngestURL(BaseModel):
    """通过 URL 摄取网页"""

    url: str = Field(..., description="要摄取的网页 URL")
    title: str | None = None
    metadata: dict[str, Any] = {}

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL 必须以 http:// 或 https:// 开头")
        return v


class DocumentIngestText(BaseModel):
    """直接摄取纯文本"""

    text: str = Field(..., min_length=10, description="要摄取的文本内容")
    title: str = Field(..., min_length=1, description="文档标题（必填）")
    metadata: dict[str, Any] = {}


# ── 文档元数据 ────────────────────────────────────────────────────────


class DocumentBase(BaseModel):
    id: UUID
    title: str | None
    source_type: DocumentSourceType
    source_url: str | None
    file_name: str | None
    chunk_count: int
    embedding_model: str
    status: DocumentStatus
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(DocumentBase):
    """文档详情响应"""

    error_message: str | None = None


class DocumentListResponse(BaseModel):
    """文档列表响应"""

    items: list[DocumentResponse]
    total: int
    page: int = 1
    size: int = 20


class DocumentIngestResponse(BaseModel):
    """摄取任务响应"""

    doc_id: UUID
    status: DocumentStatus
    chunk_count: int = 0
    message: str = ""


# ── 检索相关 ──────────────────────────────────────────────────────────


class ChunkResult(BaseModel):
    """单个文档块检索结果"""

    chunk_id: str
    text: str
    score: float
    doc_id: str | None = None
    title: str | None = None
    source_url: str | None = None
    source_type: str = "internal"
    section: str | None = None
    metadata: dict[str, Any] = {}


class SearchRequest(BaseModel):
    """知识库搜索请求"""

    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] = Field(
        default={}, description="元数据过滤，如 {source_type: 'pdf', language: 'zh'}"
    )


class SearchResponse(BaseModel):
    """知识库搜索响应"""

    query: str
    results: list[ChunkResult]
    total: int
