"""
Embedding 模型封装
统一接口，底层支持 Qwen text-embedding-v3 和 OpenAI text-embedding-3-small
两者均通过 OpenAI 兼容接口调用
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings


class EmbeddingClient:
    """
    统一 Embedding 客户端。
    Qwen 和 OpenAI 均用 HTTP 直接调用（避免 langchain embedding 的额外封装层）。
    支持批量向量化，自动分批。
    """

    def __init__(self) -> None:
        cfg = settings.get_embedding_config()
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        self.api_key = cfg["api_key"]
        self.dimensions = cfg["dimensions"]

        # 两个 provider 的 API endpoint
        if self.provider == "qwen":
            self.base_url = cfg.get("base_url", settings.qwen_base_url)
        else:
            self.base_url = "https://api.openai.com/v1"

        self.endpoint = f"{self.base_url}/embeddings"

        # 批量大小：Qwen 最大 25 条/批，OpenAI 最大 100 条/批
        self.batch_size = 25 if self.provider == "qwen" else 100

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        批量向量化文本列表，返回向量列表。
        自动分批处理超量文本。
        """
        if not texts:
            return []

        all_vectors: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                vectors = await self._embed_batch(client, batch)
                all_vectors.extend(vectors)

        return all_vectors

    async def embed_query(self, text: str) -> list[float]:
        """单条查询向量化（检索时使用）"""
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def _embed_batch(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        """调用 API 向量化一批文本"""
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }

        # Qwen text-embedding-v3 支持指定维度（降维节省存储）
        if self.provider == "qwen" and self.dimensions:
            payload["dimensions"] = self.dimensions

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = await client.post(self.endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # 标准 OpenAI 兼容格式：data[i].embedding
        return [item["embedding"] for item in data["data"]]

    def embed_texts_sync(self, texts: list[str]) -> list[list[float]]:
        """同步版本（供非 async 上下文使用）"""
        return asyncio.run(self.embed_texts(texts))

    def embed_query_sync(self, text: str) -> list[float]:
        """同步查询向量化"""
        return asyncio.run(self.embed_query(text))


# 模块级单例
_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
