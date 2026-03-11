"""
ResearchMind Pro — MCP Server
标准 Model Context Protocol 服务端，让 Claude Desktop 等 AI 客户端
直接调用 ResearchMind 的研究和检索能力。

工具列表：
  1. research_task       — 发起完整研究任务，返回报告
  2. search_knowledge_base — 检索内部知识库
  3. list_recent_tasks   — 查看最近任务列表

运行：
  uv run python -m app.mcp_server.server
  或
  uv run python app/mcp_server/server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# 确保能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


async def tool_research_task(query: str, depth: str = "deep") -> str:
    """
    发起一个研究任务，等待完成后返回完整报告。
    适合需要深度研究的场景，会调用多个 Agent 协作。

    Args:
        query: 研究问题或任务描述
        depth: 研究深度，quick=快速（30s内）或 deep=深度（2-3分钟）
    """
    import httpx

    base_url = os.getenv("RESEARCHMIND_API_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=180.0) as client:
        # 创建任务
        resp = await client.post(
            f"{base_url}/api/v1/tasks",
            json={"query": query, "depth": depth},
            headers={"X-User-Id": "mcp-client"},
        )
        resp.raise_for_status()
        task_id = resp.json()["id"]

        # SSE 流式等待完成
        report = ""
        error  = ""

        async with client.stream(
            "GET",
            f"{base_url}/api/v1/tasks/{task_id}/stream",
            headers={"X-User-Id": "mcp-client"},
            timeout=180.0,
        ) as stream:
            async for line in stream.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line[5:].strip())
                    event = data.get("event", "")

                    if event == "task_completed":
                        report = data.get("data", {}).get("report", "")
                        break
                    elif event == "task_failed":
                        error = data.get("data", {}).get("message", "未知错误")
                        break
                    elif event == "hitl_required":
                        # MCP 场景自动 approve（无人工交互）
                        await client.post(
                            f"{base_url}/api/v1/tasks/{task_id}/approve",
                            json={"action": "approve"},
                            headers={"X-User-Id": "mcp-client"},
                        )
                except (json.JSONDecodeError, KeyError):
                    continue

        if error:
            return f"任务失败：{error}"
        if report:
            return report
        return f"任务 {task_id} 已提交，请稍后查询结果。"


async def tool_search_knowledge_base(query: str, top_k: int = 5) -> str:
    """
    在内部知识库中进行语义搜索，返回相关文档片段。
    适合快速查找已有资料，不需要完整研究流程。

    Args:
        query: 搜索查询词
        top_k: 返回结果数量（1-10）
    """
    import httpx

    base_url = os.getenv("RESEARCHMIND_API_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/api/v1/kb/search",
            json={"query": query, "top_k": min(top_k, 10)},
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        return f"知识库中未找到与「{query}」相关的内容。"

    lines = [f"知识库搜索结果（共 {len(results)} 条）：\n"]
    for i, r in enumerate(results, 1):
        source = r.get("title") or r.get("source_url") or "内部文档"
        score  = r.get("score", 0)
        text   = r.get("text", "")[:400]
        lines.append(f"[{i}] 来源: {source} | 相关度: {score:.3f}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


async def tool_list_recent_tasks(limit: int = 5) -> str:
    """
    列出最近的研究任务及其状态。

    Args:
        limit: 返回任务数量（1-20）
    """
    import httpx

    base_url = os.getenv("RESEARCHMIND_API_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{base_url}/api/v1/tasks",
            params={"size": min(limit, 20)},
            headers={"X-User-Id": "mcp-client"},
        )
        resp.raise_for_status()
        data = resp.json()

    items = data.get("items", [])
    if not items:
        return "暂无研究任务记录。"

    lines = [f"最近 {len(items)} 条研究任务：\n"]
    for t in items:
        status   = t.get("status", "")
        query    = t.get("query", "")[:60]
        task_id  = str(t.get("id", ""))[:8]
        created  = t.get("created_at", "")[:10]
        lines.append(f"• [{task_id}] {status:12s} {created}  {query}...")

    return "\n".join(lines)


# ── MCP Server 主循环（stdio transport）──────────────────────────────

TOOL_REGISTRY = {
    "research_task": {
        "fn":          tool_research_task,
        "description": "发起完整研究任务，多 Agent 协作生成报告",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "研究问题"},
                "depth": {"type": "string", "enum": ["quick", "deep"], "default": "deep"},
            },
            "required": ["query"],
        },
    },
    "search_knowledge_base": {
        "fn":          tool_search_knowledge_base,
        "description": "在知识库中语义搜索相关文档片段",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    "list_recent_tasks": {
        "fn":          tool_list_recent_tasks,
        "description": "列出最近的研究任务及完成状态",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
        },
    },
}


async def handle_request(request: dict) -> dict:
    """处理单条 JSON-RPC 请求"""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities":    {"tools": {}},
            "serverInfo":      {"name": "researchmind-mcp", "version": "2.0.0"},
        })

    elif method == "tools/list":
        tools = [
            {
                "name":        name,
                "description": info["description"],
                "inputSchema": info["inputSchema"],
            }
            for name, info in TOOL_REGISTRY.items()
        ]
        return ok({"tools": tools})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in TOOL_REGISTRY:
            return err(-32601, f"未知工具: {tool_name}")

        try:
            result_text = await TOOL_REGISTRY[tool_name]["fn"](**arguments)
            return ok({
                "content": [{"type": "text", "text": result_text}],
                "isError":  False,
            })
        except Exception as e:
            return ok({
                "content": [{"type": "text", "text": f"工具执行失败: {e}"}],
                "isError":  True,
            })

    elif method == "notifications/initialized":
        return None   # 通知不需要回复

    else:
        return err(-32601, f"未知方法: {method}")


async def run_stdio_server():
    """标准 stdio transport MCP Server"""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()

    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    while True:
        try:
            # 读取 Content-Length header
            header = await reader.readline()
            if not header:
                break

            header_str = header.decode().strip()
            if not header_str.startswith("Content-Length:"):
                continue

            content_length = int(header_str.split(":")[1].strip())

            # 读取空行分隔符
            await reader.readline()

            # 读取消息体
            body = await reader.readexactly(content_length)
            request = json.loads(body)

            response = await handle_request(request)
            if response is None:
                continue

            response_str = json.dumps(response, ensure_ascii=False)
            response_bytes = response_str.encode()
            header_bytes = f"Content-Length: {len(response_bytes)}\r\n\r\n".encode()

            writer.write(header_bytes + response_bytes)
            await writer.drain()

        except asyncio.IncompleteReadError:
            break
        except Exception as e:
            sys.stderr.write(f"MCP Server 错误: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    asyncio.run(run_stdio_server())
