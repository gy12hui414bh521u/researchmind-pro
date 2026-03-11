"""
Agent 工具集
LangChain Tool 格式，供 Research Agent 调用
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.config import settings


@tool
async def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """
    在内部知识库中检索相关信息。
    返回格式化的检索结果文本，每条包含来源和相关内容。

    Args:
        query: 检索查询词
        top_k: 返回结果数量，默认 5
    """
    from app.rag.retriever import retrieve

    try:
        result = await retrieve(query=query, top_k=min(top_k, 10))
    except Exception as e:
        return f"检索失败：{e}"

    if not result.chunks:
        return "知识库中未找到相关内容。"

    lines = [f"检索到 {len(result.chunks)} 条相关内容（策略: {result.strategy}）：\n"]
    for i, chunk in enumerate(result.chunks, 1):
        source = chunk.title or chunk.source_url or "内部文档"
        lines.append(f"[{i}] 来源: {source} | 相关度: {chunk.score:.3f}")
        lines.append(chunk.text[:400])
        lines.append("")

    return "\n".join(lines)


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """
    通过 Tavily 搜索实时网络信息。
    仅在知识库覆盖不足时使用。

    Args:
        query: 搜索查询词
        max_results: 最大结果数，默认 5
    """
    if not settings.has_tavily:
        return "Web Search 未启用（未配置 TAVILY_API_KEY）。请使用知识库检索代替。"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                    "include_raw_content": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        lines = [f"网络搜索结果（{len(data.get('results', []))} 条）：\n"]

        if data.get("answer"):
            lines.append(f"综合答案：{data['answer']}\n")

        for i, r in enumerate(data.get("results", []), 1):
            lines.append(f"[{i}] {r.get('title', '无标题')}")
            lines.append(f"    URL: {r.get('url', '')}")
            lines.append(f"    {r.get('content', '')[:300]}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Web Search 失败：{e}"


@tool
def get_current_date() -> str:
    """
    获取当前日期，用于报告中需要标注时效性的场景。
    """
    from datetime import datetime

    return datetime.now().strftime("%Y年%m月%d日")


# 工具注册表
ALL_TOOLS = [search_knowledge_base, web_search, get_current_date]
RESEARCH_TOOLS = [search_knowledge_base, web_search, get_current_date]
