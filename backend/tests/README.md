# Task 5.1 — 测试套件使用指南

## 目录结构

```
tests/
├── conftest.py                     # 共享 Fixtures（DB / Client / Mock LLM）
├── pytest.ini                      # 测试配置 & 标记定义
│
├── unit/                           # 单元测试（70%，无外部依赖）
│   ├── api/
│   │   └── test_routes.py         # Health / Tasks / Knowledge 路由
│   ├── rag/
│   │   └── test_rag_pipeline.py   # 分块 / Embedding / 检索 / 去重
│   └── models/
│       └── test_models.py         # Pydantic 模型验证
│
├── integration/                    # 集成测试（20%，Mock LLM）
│   └── agents/
│       └── test_agents.py         # Planner / Researcher / Writer / Critic / LangGraph
│
└── eval/                           # Eval 测试（Golden Dataset）
    └── test_golden_dataset.py      # 20 条标准问答，Hit Rate@5 验证
```

---

## 安装依赖

```bash
cd backend
uv add --dev pytest pytest-asyncio pytest-mock httpx aiosqlite
```

---

## 运行方式

### 1. 快速验证（仅单元测试，~10秒）
```bash
cd backend
uv run pytest tests/unit/ -v
```

### 2. CI Pipeline（单元 + 集成，~30秒）
```bash
uv run pytest tests/unit/ tests/integration/ -v --tb=short
```

### 3. Eval 评估（Golden Dataset，~20秒）
```bash
uv run pytest tests/eval/ -m eval -v -s
```

### 4. 完整套件
```bash
uv run pytest tests/ -m "unit or integration or eval" -v
```

### 5. 覆盖率报告
```bash
uv run pytest tests/unit/ --cov=app --cov-report=html --cov-report=term-missing
# 报告生成在 htmlcov/index.html
```

---

## 预期测试结果

### 单元测试（tests/unit/）

```
tests/unit/api/test_routes.py
  TestHealthRoutes
    ✅ test_health_returns_ok
    ✅ test_health_detail_structure
    ✅ test_health_detail_degraded_when_db_fails

  TestTaskRoutes
    ✅ test_create_task_returns_201
    ✅ test_create_task_depth_validation
    ✅ test_create_task_empty_query_rejected
    ✅ test_list_tasks_empty
    ✅ test_list_tasks_pagination
    ✅ test_get_task_not_found
    ✅ test_get_task_detail
    ✅ test_cancel_task
    ✅ test_cancel_nonexistent_task
    ✅ test_approve_task_without_hitl_flag

  TestKnowledgeRoutes
    ✅ test_ingest_text_returns_202
    ✅ test_ingest_text_idempotent
    ✅ test_ingest_url_returns_202
    ✅ test_ingest_file_pdf
    ✅ test_ingest_file_unsupported_type
    ✅ test_list_documents_empty
    ✅ test_delete_document_not_found
    ✅ test_kb_search
    ✅ test_kb_stats

tests/unit/rag/test_rag_pipeline.py
  TestTextChunking
    ✅ test_chunk_size_within_limit
    ✅ test_chunk_count_reasonable
    ✅ test_chunk_overlap_exists
    ✅ test_empty_text_returns_empty_list
    ✅ test_short_text_single_chunk
    ✅ test_pdf_chunk_preserves_structure

  TestIngestion
    ✅ test_ingest_text_success
    ✅ test_ingest_text_returns_chunk_count
    ✅ test_ingest_handles_embedding_error
    ✅ test_ingest_deduplication_by_hash

  TestRetrieval
    ✅ test_retrieve_returns_results
    ✅ test_retrieve_score_range
    ✅ test_retrieve_respects_top_k
    ✅ test_retrieve_with_metadata_filter
    ✅ test_get_collection_stats
    ✅ test_delete_doc_vectors

  TestDocumentDedup
    ✅ test_hash_deterministic
    ✅ test_different_content_different_hash
    ✅ test_hash_length_is_64

tests/unit/models/test_models.py
  TestTaskModels       ✅ 6 passed
  TestDocumentModels   ✅ 6 passed

─────────────────────────────────────
单元测试合计：约 48 个，预期全部通过
```

### 集成测试（tests/integration/）

```
tests/integration/agents/test_agents.py
  TestPlannerAgent
    ✅ test_planner_generates_subtasks
    ✅ test_planner_sets_hitl_flag
    ✅ test_planner_depth1_skips_hitl
    ✅ test_planner_handles_llm_json_error
    ✅ test_planner_empty_query

  TestResearchAgent
    ✅ test_research_retrieves_from_kb
    ✅ test_research_parallel_queries

  TestWriterAgent
    ✅ test_writer_generates_markdown
    ✅ test_writer_includes_sources
    ✅ test_writer_empty_chunks_handled

  TestCriticAgent
    ✅ test_critic_approves_good_report
    ✅ test_critic_requests_revision
    ✅ test_critic_max_iterations_stops_loop

  TestLangGraphWorkflow
    ✅ test_happy_path_completes
    ✅ test_hitl_pause_resume
    ✅ test_workflow_handles_llm_timeout

集成测试合计：约 16 个，预期全部通过
```

### Eval 测试（tests/eval/）

```
tests/eval/test_golden_dataset.py
  TestRAGEval
    ✅ test_hit_rate_meets_target        Hit Rate: 100.00% ≥ 85% ✓
    ✅ test_keyword_hit_rate             Keyword Hit Rate: 100.00% ≥ 80% ✓
    ✅ test_error_rate_below_threshold   Error Rate: 0.00% < 1% ✓
    ✅ test_per_category_hit_rate        各类别 ≥ 80% ✓
    ✅ test_golden_dataset_integrity     格式完整 ✓
    ✅ test_no_duplicate_ids             无重复 ✓

  TestEvalReport
    ✅ test_generate_eval_report         报告生成成功，pass: true

Eval 输出示例：
  [Eval] Hit Rate: 100.00%
  [Eval] Avg Keyword Hit Rate: 100.00%
  [Eval] Avg Latency: 0.1ms
  [Eval] Error Rate: 0.00%
```

### 覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| `app/api/` | ≥ 85% | 路由层全覆盖 |
| `app/rag/` | ≥ 80% | 核心 Pipeline |
| `app/models/` | ≥ 90% | 模型验证 |
| `app/agents/` | ≥ 75% | Mock LLM 集成测试 |
| **整体** | **≥ 80%** | **SDD NFR-M01 要求** |

---

## 注意事项

1. **不需要真实 API Key**：所有测试使用 Mock LLM / Mock Qdrant，CI 中无需配置 OPENAI_API_KEY。
2. **不需要 Docker**：单元测试使用 SQLite in-memory，无需启动 PostgreSQL/Redis/Qdrant。
3. **集成测试**：同样使用 Mock，但依赖 `app.*` 模块能正常 import（需要 `uv sync`）。
4. **Eval 真实运行**：如需测试真实检索质量，去掉 `mock_retriever=True` 参数，需要 Qdrant 已预填充 Golden 文档。
