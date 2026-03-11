import asyncio
from app.rag.ingestion import clean_text, split_by_tokens_approx, ingest_text
from app.rag.retriever import retrieve

# 测试 1：文本清洗
text = '  Hello   World  \n\n\n  这是测试  '
cleaned = clean_text(text)
print(f'✅ 清洗: [{cleaned}]')

# 测试 2：分块
long_text = '人工智能是计算机科学的一个分支。' * 50
chunks = split_by_tokens_approx(long_text, chunk_size=200)
print(f'✅ 分块: {len(chunks)} 个 chunk')

# 测试 3：摄取 + 检索（需要 Qdrant + API Key）
async def test_e2e():
    result = await ingest_text(
        text='大模型是2024年最重要的技术趋势，RAG技术让LLM能够访问外部知识库。',
        doc_id='test-001',
        title='测试文档',
    )
    print(f'✅ 摄取: {result.chunk_count} chunks, 耗时 {result.elapsed_s}s')

    r = await retrieve('什么是RAG技术', top_k=3)
    print(f'✅ 检索: {len(r.chunks)} 条结果, 策略={r.strategy}')
    if r.chunks:
        print(f'   最高分: {r.chunks[0].score:.3f}')

asyncio.run(test_e2e())
