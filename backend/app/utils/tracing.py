"""
LangSmith 链路追踪配置
LANGCHAIN_TRACING_V2=true 时，所有 LangChain/LangGraph 调用自动上传到 LangSmith
"""

from __future__ import annotations

import os


def setup_langsmith() -> bool:
    """
    配置 LangSmith 环境变量。
    在 FastAPI lifespan 中调用。
    返回是否成功启用。
    """
    from app.config import settings

    if not settings.langchain_tracing_v2 or not settings.langchain_api_key:
        return False

    os.environ["LANGCHAIN_TRACING_V2"]  = "true"
    os.environ["LANGCHAIN_API_KEY"]     = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"]     = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"]    = settings.langchain_endpoint

    return True


def get_run_url(run_id: str) -> str:
    """生成 LangSmith Run URL（用于日志输出）"""
    from app.config import settings
    project = settings.langchain_project
    return f"https://smith.langchain.com/projects/{project}/runs/{run_id}"
