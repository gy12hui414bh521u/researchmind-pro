"""
共享 Fixtures — 所有测试层通用（修复版 v4）

修复要点：
1. 原生 SQL 建表，包含 context 列
2. tasks.id 用 Python uuid4() 生成标准 UUID（带连字符），
   避免 SQLite hex(randomblob) vs FastAPI UUID 路由参数不匹配
3. depth → "deep"/"quick"
4. mock_emb_client 对齐 embed_query / embed_texts
5. mock_qdrant 对齐 query_points + close()
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

# ── 事件循环 ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── 建表 DDL ──────────────────────────────────────────────────────────
# 关键：id 不用 SQLite 的 hex(randomblob)，
# 而是留空让应用层自己生成（repositories.py 的 INSERT RETURNING * 会返回 DB 生成的 id）。
# 但 SQLite 的 hex(randomblob) 生成的是无连字符格式，
# 而 FastAPI 路由参数 task_id: UUID 会把它格式化为带连字符版，导致 SELECT 找不到。
# 解决：DDL 里不设 DEFAULT，让 Python 端（repositories.py）传入 uuid4()。
# 但 repositories.py 的 INSERT 没传 id——所以在 DDL 里改用 uuid() 函数也不行。
# 最终方案：注册一个 SQLite 自定义函数 gen_uuid() 来生成标准 UUID。

CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    query           TEXT NOT NULL,
    depth           TEXT NOT NULL DEFAULT 'deep',
    context         TEXT DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    plan            TEXT,
    result          TEXT,
    quality_score   REAL,
    iteration_count INTEGER DEFAULT 0,
    hitl_required   INTEGER DEFAULT 0,
    hitl_approved   INTEGER,
    token_input     INTEGER DEFAULT 0,
    token_output    INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    error_code      TEXT,
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT
)
"""

CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    doc_hash        TEXT NOT NULL UNIQUE,
    title           TEXT,
    source_type     TEXT NOT NULL,
    source_url      TEXT,
    file_name       TEXT,
    chunk_count     INTEGER DEFAULT 0,
    embedding_model TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    metadata        TEXT DEFAULT '{}',
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""


# ── 测试数据库（SQLite in-memory）────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

def _register_uuid_func(conn):
    """注册 SQLite 自定义函数，模拟 PostgreSQL gen_random_uuid()"""
    import uuid
    conn.create_function("gen_uuid", 0, lambda: str(uuid.uuid4()))

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    import uuid as _uuid
    from sqlalchemy import event as sa_event

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # 注册 gen_uuid() 函数到每个新连接
    @sa_event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn, _):
        dbapi_conn.create_function("gen_uuid", 0, lambda: str(_uuid.uuid4()))

    # 建表，id DEFAULT 用 gen_uuid()
    create_tasks = CREATE_TASKS_TABLE.replace(
        "id              TEXT PRIMARY KEY,",
        "id              TEXT PRIMARY KEY DEFAULT (gen_uuid()),"
    )
    create_docs = CREATE_DOCUMENTS_TABLE.replace(
        "id              TEXT PRIMARY KEY,",
        "id              TEXT PRIMARY KEY DEFAULT (gen_uuid()),"
    )

    async with engine.begin() as conn:
        await conn.execute(text(create_tasks))
        await conn.execute(text(create_docs))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session = async_sessionmaker(db_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


# ── FastAPI 测试客户端 ────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app
    from app.db.database import get_db
    from app.config import settings

    settings.auth_disabled = True

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ── Mock Embedding Client ─────────────────────────────────────────────

@pytest.fixture
def mock_emb_client():
    client = MagicMock()
    client.embed_query = AsyncMock(return_value=[0.15] * 1536)
    client.embed_texts = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])
    return client

@pytest.fixture
def mock_embeddings(mock_emb_client):
    return mock_emb_client


# ── Mock LLM ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(
        content='{"subtasks": ["分析市场规模", "竞争格局", "技术趋势"]}'
    ))
    return llm


# ── Mock Qdrant ───────────────────────────────────────────────────────

@pytest.fixture
def mock_qdrant():
    qdrant = MagicMock()
    _hit = MagicMock(
        id="chunk-001",
        score=0.92,
        payload={
            "chunk_id":    "chunk-001",
            "text":        "大模型市场2024年规模超过千亿美元",
            "title":       "AI市场报告",
            "doc_id":      "doc-001",
            "source_type": "internal",
        }
    )
    qdrant.query_points   = AsyncMock(return_value=MagicMock(points=[_hit]))
    qdrant.search         = AsyncMock(return_value=[_hit])
    qdrant.upsert         = AsyncMock(return_value=MagicMock(status="completed"))
    qdrant.delete         = AsyncMock(return_value=MagicMock(status="completed"))
    qdrant.get_collection = AsyncMock(return_value=MagicMock(
        vectors_count=1000, points_count=1000, status="green",
    ))
    qdrant.close = AsyncMock()
    return qdrant


# ── 样本数据 ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_task_create():
    return {
        "query": "分析2024年大模型市场竞争格局，重点关注头部厂商差异化策略",
        "depth": "deep",
    }


@pytest.fixture
def sample_doc_text():
    return (
        "大型语言模型（LLM）是一种基于深度学习的自然语言处理模型。\n\n"
        "2024年，OpenAI、Anthropic、Google等头部厂商持续推出新一代模型。\n\n"
        "国内方面，阿里通义千问、百度文心等模型也取得了显著进展。\n\n"
        "LLM的核心能力包括：文本生成、代码编写、逻辑推理和知识问答。\n\n"
        "在企业应用场景中，RAG（检索增强生成）成为落地的主要技术路径。\n\n"
    ) * 20