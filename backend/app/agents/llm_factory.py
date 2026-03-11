"""
LLM 工厂
根据 config 中的 model_spec 创建对应的 ChatOpenAI 实例。
DeepSeek / Qwen 均走 OpenAI 兼容接口，统一用 ChatOpenAI。
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


def create_llm(spec: str, **kwargs) -> ChatOpenAI:
    """
    根据 model spec 创建 ChatOpenAI 实例。
    kwargs 可覆盖默认参数，如 temperature、max_tokens。
    """
    cfg = settings.get_llm_config(spec)

    # Anthropic 走独立 SDK
    if cfg.get("_provider") == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=cfg["model"],
            api_key=cfg["api_key"],
            temperature=kwargs.get("temperature", cfg.get("temperature", 0.1)),
            max_tokens=kwargs.get("max_tokens", 1024),
        )

    # DeepSeek / Qwen / OpenAI 统一走 ChatOpenAI
    init_kwargs = {
        "model":       cfg["model"],
        "api_key":     cfg["api_key"],
        "temperature": cfg.get("temperature", 0.1),
    }
    if "base_url" in cfg:
        init_kwargs["base_url"] = cfg["base_url"]

    # 允许外部覆盖
    init_kwargs.update(kwargs)

    return ChatOpenAI(**init_kwargs)


# ── 各 Agent 专用 LLM（带缓存，避免重复初始化）─────────────────────

@lru_cache(maxsize=1)
def get_planner_llm() -> ChatOpenAI:
    return create_llm(settings.planner_model_spec, max_tokens=settings.max_tokens_planner)

@lru_cache(maxsize=1)
def get_writer_llm() -> ChatOpenAI:
    return create_llm(settings.writer_model_spec, max_tokens=settings.max_tokens_writer)

@lru_cache(maxsize=1)
def get_analyst_llm() -> ChatOpenAI:
    return create_llm(settings.analyst_model_spec, max_tokens=settings.max_tokens_default)

@lru_cache(maxsize=1)
def get_research_llm() -> ChatOpenAI:
    return create_llm(settings.research_model_spec, max_tokens=settings.max_tokens_default)

@lru_cache(maxsize=1)
def get_critic_llm() -> ChatOpenAI:
    return create_llm(settings.critic_model_spec, max_tokens=settings.max_tokens_default)
