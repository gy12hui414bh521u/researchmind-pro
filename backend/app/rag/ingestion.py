"""
文档摄取 Pipeline
流程：原始文档 → 解析 → 清洗 → 分块 → 向量化 → 存入 Qdrant

支持输入类型：
  - 纯文本 (str)
  - PDF 文件 (bytes)
  - 网页 URL (str, 以 http 开头)
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

from app.config import settings
from app.rag.embeddings import get_embedding_client

# ── 数据类 ────────────────────────────────────────────────────────────


@dataclass
class DocumentChunk:
    """单个文档分块"""

    text: str
    chunk_index: int
    doc_id: str
    doc_hash: str
    title: str = ""
    source_url: str = ""
    source_type: str = "text"
    section: str = ""
    language: str = "zh"
    metadata: dict = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return f"{self.doc_hash[:12]}_{self.chunk_index:04d}"


@dataclass
class IngestionResult:
    """摄取结果"""

    doc_id: str
    doc_hash: str
    chunk_count: int
    success: bool
    error: str = ""
    elapsed_s: float = 0.0


# ── 文本清洗 ──────────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    """清洗文本：去除噪声，统一格式"""
    # 替换多余空白
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 去除常见 PDF 噪声：页码、页眉页脚（简单规则）
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # 去除零宽字符
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

    return text.strip()


def detect_language(text: str) -> str:
    """简单语言检测：中文字符占比 > 20% 判断为中文"""
    if not text:
        return "en"
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    ratio = chinese_chars / max(len(text), 1)
    return "zh" if ratio > 0.2 else "en"


# ── 文本分块 ──────────────────────────────────────────────────────────


def split_by_tokens_approx(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """
    近似 token 分块（以字符数估算：中文 1 字符 ≈ 1 token，英文 1 词 ≈ 1.3 tokens）。
    优先在段落边界（\n\n）切分，其次在句子边界（。.!?）切分。
    """
    if not text:
        return []

    # 先按段落分割
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # 单段落本身超过 chunk_size，在句子边界切
        if len(para) > chunk_size * 1.5:
            # 句子分割
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(current) + len(sent) <= chunk_size:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = sent
        else:
            if len(current) + len(para) + 2 <= chunk_size:
                current = (current + "\n\n" + para).strip() if current else para
            else:
                if current:
                    chunks.append(current)
                current = para

    if current:
        chunks.append(current)

    # 处理 overlap：每个 chunk 头部加上上一个 chunk 的尾部
    if chunk_overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-chunk_overlap:]
            overlapped.append((prev_tail + "\n" + chunks[i]).strip())
        return overlapped

    return chunks


def split_markdown(text: str, chunk_size: int = 512) -> list[tuple[str, str]]:
    """
    Markdown 文档按标题切分。
    返回 [(section_title, content), ...]
    """
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_content: list[str] = []

    for line in text.split("\n"):
        header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if header_match:
            if current_content:
                sections.append((current_title, "\n".join(current_content).strip()))
            current_title = header_match.group(2).strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections.append((current_title, "\n".join(current_content).strip()))

    # 太长的 section 再细分
    result: list[tuple[str, str]] = []
    for title, content in sections:
        if len(content) > chunk_size * 2:
            sub_chunks = split_by_tokens_approx(content, chunk_size)
            for sc in sub_chunks:
                result.append((title, sc))
        elif content:
            result.append((title, content))

    return result


# ── PDF 解析 ──────────────────────────────────────────────────────────


async def parse_pdf(pdf_bytes: bytes) -> str:
    """
    解析 PDF 为纯文本。
    优先使用 LlamaParse（如配置），否则 fallback 到 pymupdf。
    """
    # 尝试 LlamaParse（高质量，需要 API Key）
    if settings.has_llama_cloud:
        try:
            return await _parse_pdf_llama(pdf_bytes)
        except Exception as e:
            print(f"⚠️  LlamaParse 失败，fallback 到 pymupdf: {e}")

    # Fallback：pymupdf
    return await _parse_pdf_pymupdf(pdf_bytes)


async def _parse_pdf_pymupdf(pdf_bytes: bytes) -> str:
    """使用 pymupdf 解析 PDF（本地，免费）"""
    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        raise RuntimeError(
            "pymupdf 未安装，请运行：uv add pymupdf\n或配置 LLAMA_CLOUD_API_KEY 使用 LlamaParse"
        )


async def _parse_pdf_llama(pdf_bytes: bytes) -> str:
    """使用 LlamaParse 解析 PDF（云端，高质量）"""
    import asyncio

    import httpx

    headers = {"Authorization": f"Bearer {settings.llama_cloud_api_key}"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 上传文件
        resp = await client.post(
            "https://api.cloud.llamaindex.ai/api/parsing/upload",
            headers=headers,
            files={"file": ("document.pdf", pdf_bytes, "application/pdf")},
        )
        resp.raise_for_status()
        job_id = resp.json()["id"]

        # 轮询状态
        for _ in range(30):
            await asyncio.sleep(3)
            status_resp = await client.get(
                f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}",
                headers=headers,
            )
            status = status_resp.json().get("status")
            if status == "SUCCESS":
                break
            elif status == "ERROR":
                raise RuntimeError("LlamaParse 解析失败")

        # 获取结果
        result_resp = await client.get(
            f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/markdown",
            headers=headers,
        )
        result_resp.raise_for_status()
        return result_resp.json().get("markdown", "")


# ── 网页抓取 ──────────────────────────────────────────────────────────


async def fetch_url(url: str) -> tuple[str, str]:
    """
    抓取网页内容，返回 (title, text)。
    使用 httpx + 简单 HTML 清洗（不依赖 playwright）。
    """
    import html

    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        raw_html = resp.text

    # 简单提取：去除 script/style/nav，保留 body 文字
    # 提取 title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = html.unescape(title_match.group(1).strip()) if title_match else url

    # 移除不需要的标签
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # 去除所有 HTML 标签
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = clean_text(text)

    return title, text


# ── 主摄取函数 ────────────────────────────────────────────────────────


async def ingest_text(
    text: str,
    doc_id: str,
    title: str = "",
    source_url: str = "",
    source_type: str = "text",
    metadata: dict = None,
) -> IngestionResult:
    """
    摄取纯文本到 Qdrant。
    这是核心函数，PDF/URL 解析后都调用这里。
    """
    if metadata is None:
        metadata = {}
    start = time.time()

    # 1. 清洗
    text = clean_text(text)
    if not text:
        return IngestionResult(
            doc_id=doc_id, doc_hash="", chunk_count=0, success=False, error="清洗后文本为空"
        )

    # 2. 计算 hash（用于幂等）
    doc_hash = hashlib.sha256(text.encode()).hexdigest()

    # 3. 分块
    language = detect_language(text)
    is_markdown = source_type == "markdown" or text.startswith("#")

    chunks_with_section: list[tuple[str, str]]
    if is_markdown:
        chunks_with_section = split_markdown(text, settings.chunk_size)
    else:
        raw_chunks = split_by_tokens_approx(text, settings.chunk_size, settings.chunk_overlap)
        chunks_with_section = [("", c) for c in raw_chunks]

    if not chunks_with_section:
        return IngestionResult(
            doc_id=doc_id, doc_hash=doc_hash, chunk_count=0, success=False, error="分块结果为空"
        )

    # 4. 构建 DocumentChunk 列表
    doc_chunks = [
        DocumentChunk(
            text=chunk_text,
            chunk_index=i,
            doc_id=doc_id,
            doc_hash=doc_hash,
            title=title,
            source_url=source_url,
            source_type=source_type,
            section=section,
            language=language,
            metadata=metadata,
        )
        for i, (section, chunk_text) in enumerate(chunks_with_section)
        if chunk_text.strip()
    ]

    # 5. 向量化（批量）
    emb_client = get_embedding_client()
    texts_to_embed = [c.text for c in doc_chunks]
    try:
        vectors = await emb_client.embed_texts(texts_to_embed)
    except Exception as e:
        return IngestionResult(
            doc_id=doc_id,
            doc_hash=doc_hash,
            chunk_count=0,
            success=False,
            error=f"Embedding 失败: {e}",
        )

    # 6. 存入 Qdrant
    try:
        await _upsert_to_qdrant(doc_chunks, vectors)
    except Exception as e:
        return IngestionResult(
            doc_id=doc_id,
            doc_hash=doc_hash,
            chunk_count=0,
            success=False,
            error=f"Qdrant 写入失败: {e}",
        )

    elapsed = time.time() - start
    return IngestionResult(
        doc_id=doc_id,
        doc_hash=doc_hash,
        chunk_count=len(doc_chunks),
        success=True,
        elapsed_s=round(elapsed, 2),
    )


async def ingest_pdf(
    pdf_bytes: bytes,
    doc_id: str,
    title: str = "",
    metadata: dict = None,
) -> IngestionResult:
    """摄取 PDF 文件"""
    if metadata is None:
        metadata = {}
    try:
        text = await parse_pdf(pdf_bytes)
    except Exception as e:
        return IngestionResult(
            doc_id=doc_id, doc_hash="", chunk_count=0, success=False, error=f"PDF 解析失败: {e}"
        )
    return await ingest_text(text, doc_id, title=title, source_type="pdf", metadata=metadata)


async def ingest_url(
    url: str,
    doc_id: str,
    metadata: dict = None,
) -> IngestionResult:
    """摄取网页 URL"""
    if metadata is None:
        metadata = {}
    try:
        title, text = await fetch_url(url)
    except Exception as e:
        return IngestionResult(
            doc_id=doc_id, doc_hash="", chunk_count=0, success=False, error=f"网页抓取失败: {e}"
        )
    return await ingest_text(
        text,
        doc_id,
        title=title,
        source_url=url,
        source_type="url",
        metadata=metadata,
    )


# ── Qdrant 写入 ───────────────────────────────────────────────────────


async def _upsert_to_qdrant(
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
) -> None:
    """将 chunk + vector 批量写入 Qdrant"""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        check_compatibility=False,
    )

    # 确保 collection 存在
    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]
    if settings.qdrant_collection not in existing:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )

    # 构建 PointStruct 列表
    points = [
        PointStruct(
            id=abs(hash(chunk.chunk_id)) % (2**63),  # Qdrant 需要 uint64
            vector=vector,
            payload={
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "doc_hash": chunk.doc_hash,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "title": chunk.title,
                "source_url": chunk.source_url,
                "source_type": chunk.source_type,
                "section": chunk.section,
                "language": chunk.language,
                **chunk.metadata,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=False)
    ]

    # 分批写入（每批 100 条）
    batch_size = 100
    for i in range(0, len(points), batch_size):
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[i : i + batch_size],
        )

    await client.close()
