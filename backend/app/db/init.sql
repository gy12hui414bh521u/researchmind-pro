-- ══════════════════════════════════════════════════════════════════════
-- ResearchMind Pro — PostgreSQL 初始化 DDL
-- 由 Docker 启动时自动执行（仅首次，数据库为空时）
-- ══════════════════════════════════════════════════════════════════════

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- 支持模糊文本搜索

-- ── 用户表 ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    username     VARCHAR(64) UNIQUE NOT NULL,
    email        VARCHAR(255) UNIQUE,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE users IS '用户表';

-- 开发用默认用户（password: dev，实际生产需删除）
INSERT INTO users (id, username, email)
VALUES ('00000000-0000-0000-0000-000000000001', 'dev', 'dev@researchmind.local')
ON CONFLICT DO NOTHING;

-- ── 任务主表 ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 任务输入
    query           TEXT         NOT NULL,
    depth           VARCHAR(10)  NOT NULL DEFAULT 'deep'
                                 CHECK (depth IN ('quick', 'deep')),
    context         JSONB        DEFAULT '{}',

    -- 任务状态
    -- pending → planning → researching → analyzing → writing
    -- → reviewing → completed / failed / cancelled
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending'
                                 CHECK (status IN (
                                     'pending', 'planning', 'researching',
                                     'analyzing', 'writing', 'reviewing',
                                     'completed', 'failed', 'cancelled'
                                 )),

    -- Agent 中间产物
    plan            JSONB,          -- Planner Agent 输出的任务计划
    research_data   JSONB,          -- Research Agent 收集的原始资料
    analysis_data   JSONB,          -- Analyst Agent 的结构化分析

    -- 最终输出
    result          JSONB,          -- 完整报告 {report, sources, summary}
    quality_score   DECIMAL(4,3),   -- Critic 评分 0.000~1.000

    -- 迭代控制
    iteration_count SMALLINT     NOT NULL DEFAULT 0,
    hitl_required   BOOLEAN      NOT NULL DEFAULT FALSE,
    hitl_approved   BOOLEAN,

    -- 成本追踪
    token_input     INTEGER      NOT NULL DEFAULT 0,
    token_output    INTEGER      NOT NULL DEFAULT 0,
    cost_usd        DECIMAL(10,6) NOT NULL DEFAULT 0,

    -- 错误信息
    error_code      VARCHAR(20),
    error_message   TEXT,

    -- 时间戳
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ  GENERATED ALWAYS AS
                    (created_at + INTERVAL '90 days') STORED
);

COMMENT ON TABLE  tasks              IS '研究任务主表';
COMMENT ON COLUMN tasks.depth        IS 'quick=快速模式，deep=深度模式';
COMMENT ON COLUMN tasks.plan         IS 'Planner Agent 输出的子任务列表';
COMMENT ON COLUMN tasks.quality_score IS 'Critic 评分，低于 0.75 触发重写';
COMMENT ON COLUMN tasks.cost_usd     IS '本次任务 LLM API 总成本（美元）';
COMMENT ON COLUMN tasks.expires_at   IS '数据保留期 90 天，到期后可清理';

-- 常用查询索引
CREATE INDEX IF NOT EXISTS idx_tasks_user_status
    ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status) WHERE status IN ('pending', 'planning', 'researching', 'writing');
CREATE INDEX IF NOT EXISTS idx_tasks_created
    ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_expires
    ON tasks(expires_at);

-- ── 知识库文档元数据表 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 文档唯一标识（SHA256 of content，用于幂等摄取）
    doc_hash        VARCHAR(64)  UNIQUE NOT NULL,

    -- 文档信息
    title           TEXT,
    source_type     VARCHAR(20)  NOT NULL DEFAULT 'manual'
                                 CHECK (source_type IN (
                                     'pdf', 'markdown', 'url', 'text', 'manual'
                                 )),
    source_url      TEXT,
    file_name       VARCHAR(255),

    -- 向量化信息
    chunk_count     INTEGER      NOT NULL DEFAULT 0,
    embedding_model VARCHAR(80)  NOT NULL DEFAULT 'text-embedding-v3',

    -- 摄取状态
    -- processing → completed / failed
    status          VARCHAR(20)  NOT NULL DEFAULT 'processing'
                                 CHECK (status IN ('processing', 'completed', 'failed')),
    error_message   TEXT,

    -- 元数据（可自由扩展）
    metadata        JSONB        DEFAULT '{}',

    -- 时间戳
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  documents           IS '知识库文档元数据，向量数据存储在 Qdrant';
COMMENT ON COLUMN documents.doc_hash  IS 'SHA256(content)，保证同文档不重复摄取';
COMMENT ON COLUMN documents.metadata  IS '扩展字段：语言、作者、分类、标签等';

CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_source_type
    ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_created
    ON documents(created_at DESC);
-- 支持 title 模糊搜索
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm
    ON documents USING gin(title gin_trgm_ops);

-- ── 任务-文档关联表 ───────────────────────────────────────────────────
-- 记录哪些文档参与了哪个任务的研究（用于来源溯源）
CREATE TABLE IF NOT EXISTS task_sources (
    task_id     UUID    NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    doc_id      UUID    REFERENCES documents(id) ON DELETE SET NULL,
    -- 外部来源（URL）也需要记录
    source_url  TEXT,
    source_type VARCHAR(20) NOT NULL DEFAULT 'internal',  -- internal | web
    relevance   DECIMAL(4,3),  -- 该来源的相关度评分
    snippet     TEXT,          -- 引用的片段摘要
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (task_id, COALESCE(doc_id::TEXT, source_url, ''))
);

COMMENT ON TABLE task_sources IS '任务引用的知识来源，用于报告中的引用溯源';

CREATE INDEX IF NOT EXISTS idx_task_sources_task
    ON task_sources(task_id);

-- ── LangGraph Checkpointer 表（状态持久化）───────────────────────────
-- 由 langgraph-checkpoint-postgres 自动管理，这里预建表结构
-- 注意：langgraph 会在首次使用时自动 CREATE TABLE IF NOT EXISTS
-- 此处建表仅为提前可见

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id   TEXT        NOT NULL,
    checkpoint_ns TEXT      NOT NULL DEFAULT '',
    checkpoint_id TEXT      NOT NULL,
    parent_checkpoint_id TEXT,
    type        TEXT,
    checkpoint   JSONB      NOT NULL,
    metadata     JSONB      NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id    TEXT    NOT NULL,
    checkpoint_ns TEXT   NOT NULL DEFAULT '',
    channel      TEXT    NOT NULL,
    version      TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    blob         BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id    TEXT    NOT NULL,
    checkpoint_ns TEXT   NOT NULL DEFAULT '',
    checkpoint_id TEXT   NOT NULL,
    task_id      TEXT    NOT NULL,
    idx          INTEGER NOT NULL,
    channel      TEXT    NOT NULL,
    type         TEXT,
    blob         BYTEA   NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

COMMENT ON TABLE checkpoints       IS 'LangGraph 状态检查点，支持 HiTL 断点续传';
COMMENT ON TABLE checkpoint_blobs  IS 'LangGraph 状态二进制数据';
COMMENT ON TABLE checkpoint_writes IS 'LangGraph 待写入状态队列';

-- ── 审计日志表 ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    task_id     UUID        REFERENCES tasks(id) ON DELETE SET NULL,
    action      VARCHAR(50) NOT NULL,  -- task.create / task.approve / kb.ingest / ...
    resource    VARCHAR(50),
    detail      JSONB       DEFAULT '{}',
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE audit_logs IS '操作审计日志，保留 365 天';

CREATE INDEX IF NOT EXISTS idx_audit_logs_user
    ON audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_task
    ON audit_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created
    ON audit_logs(created_at DESC);

-- ── 自动更新 updated_at 的触发器 ─────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── 完成提示 ──────────────────────────────────────────────────────────
DO $$
BEGIN
    RAISE NOTICE '✅ ResearchMind Pro 数据库初始化完成';
    RAISE NOTICE '   Tables: users, tasks, documents, task_sources, checkpoints, audit_logs';
END $$;
