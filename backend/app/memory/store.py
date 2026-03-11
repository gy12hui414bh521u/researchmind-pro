"""
长期记忆存储
基于 LangMem + Redis，跨任务保存用户偏好、领域知识和研究历史摘要。

设计：
  - 短期记忆：LangGraph State（任务内，随任务结束消失）
  - 长期记忆：Redis Hash（跨任务，永久保留）
  - 记忆类型：user_preference / domain_context / task_summary
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.config import settings

# ── 记忆类型 ──────────────────────────────────────────────────────────

MEMORY_TYPES = {
    "user_preference": "用户偏好（报告语言、深度偏好、关注领域）",
    "domain_context": "领域背景知识（用户告知的行业背景）",
    "task_summary": "历史任务摘要（防止重复研究相同问题）",
}


class MemoryStore:
    """
    长期记忆读写接口。
    底层用 Redis Hash，key = memory:{user_id}:{memory_type}
    """

    def __init__(self):
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    # ── 写入记忆 ──────────────────────────────────────────────────────

    async def save(
        self,
        user_id: str,
        memory_type: str,
        key: str,
        value: Any,
        ttl_days: int = 90,
    ) -> None:
        """
        保存一条记忆。
        user_id + memory_type + key 唯一定位一条记忆。
        """
        r = await self._get_client()
        redis_key = f"memory:{user_id}:{memory_type}"
        entry = {
            "value": value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await r.hset(redis_key, key, json.dumps(entry, ensure_ascii=False))
        await r.expire(redis_key, ttl_days * 86400)

    async def save_task_summary(
        self,
        user_id: str,
        task_id: str,
        query: str,
        summary: str,
        keywords: list[str] | None = None,
    ) -> None:
        """保存任务完成摘要（供后续任务参考，避免重复研究）"""
        if keywords is None:
            keywords = []
        await self.save(
            user_id=user_id,
            memory_type="task_summary",
            key=task_id,
            value={
                "query": query,
                "summary": summary[:500],
                "keywords": keywords,
            },
            ttl_days=180,
        )

    async def save_user_preference(self, user_id: str, pref_key: str, pref_value: Any) -> None:
        """保存用户偏好，如 language=zh、depth=deep"""
        await self.save(user_id, "user_preference", pref_key, pref_value, ttl_days=365)

    # ── 读取记忆 ──────────────────────────────────────────────────────

    async def get(self, user_id: str, memory_type: str, key: str) -> Any | None:
        """读取单条记忆"""
        r = await self._get_client()
        redis_key = f"memory:{user_id}:{memory_type}"
        raw = await r.hget(redis_key, key)
        if not raw:
            return None
        entry = json.loads(raw)
        return entry.get("value")

    async def get_all(self, user_id: str, memory_type: str) -> dict[str, Any]:
        """读取某类型下的所有记忆"""
        r = await self._get_client()
        redis_key = f"memory:{user_id}:{memory_type}"
        raw_dict = await r.hgetall(redis_key)
        return {k: json.loads(v).get("value") for k, v in raw_dict.items()}

    async def get_recent_task_summaries(self, user_id: str, limit: int = 5) -> list[dict]:
        """获取最近 N 条任务摘要，注入 Planner 作为上下文"""
        summaries = await self.get_all(user_id, "task_summary")
        result = []
        for task_id, val in list(summaries.items())[-limit:]:
            if isinstance(val, dict):
                result.append({"task_id": task_id, **val})
        return result

    async def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """获取用户全部偏好设置"""
        return await self.get_all(user_id, "user_preference")

    async def build_memory_context(self, user_id: str, query: str) -> str:
        """
        为当前任务构建记忆上下文字符串，注入 Planner prompt。
        包含：用户偏好 + 相关历史任务摘要
        """
        prefs = await self.get_user_preferences(user_id)
        summaries = await self.get_recent_task_summaries(user_id, limit=3)

        lines = []

        if prefs:
            lines.append("【用户偏好】")
            for k, v in prefs.items():
                lines.append(f"  - {k}: {v}")

        if summaries:
            lines.append("【近期研究历史】")
            for s in summaries:
                lines.append(f"  - 问题：{s.get('query', '')}")
                lines.append(f"    摘要：{s.get('summary', '')[:200]}")

        return "\n".join(lines) if lines else ""

    # ── 删除记忆 ──────────────────────────────────────────────────────

    async def delete(self, user_id: str, memory_type: str, key: str) -> None:
        r = await self._get_client()
        redis_key = f"memory:{user_id}:{memory_type}"
        await r.hdel(redis_key, key)

    async def clear_user(self, user_id: str) -> None:
        """清除某用户全部记忆（GDPR 删除用）"""
        r = await self._get_client()
        for mtype in MEMORY_TYPES:
            await r.delete(f"memory:{user_id}:{mtype}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── 全局单例 ──────────────────────────────────────────────────────────

_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
