"""
ResearchMind Pro — 配置管理
支持 LLM Provider：DeepSeek / Qwen（阿里云百炼）/ OpenAI / Anthropic
使用 Pydantic Settings 统一管理所有配置项，支持环境变量覆盖。
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 枚举 ──────────────────────────────────────────────────────────────────────


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LLMProvider(StrEnum):
    """支持的 LLM Provider"""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


# ── 应用基础配置 ──────────────────────────────────────────────────────────────


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ResearchMind Pro"
    app_version: str = "2.0.0"
    app_description: str = "Enterprise Multi-Agent Intelligent Research System"
    environment: Environment = Environment.LOCAL
    debug: bool = False

    backend_port: int = 8000
    mcp_server_port: int = 8001
    frontend_port: int = 5173

    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    log_level: LogLevel = LogLevel.INFO
    log_json: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self.environment == Environment.LOCAL


# ── LLM Provider 配置 ─────────────────────────────────────────────────────────


class LLMSettings(BaseSettings):
    """
    多 Provider 支持。
    DeepSeek 和 Qwen 均兼容 OpenAI SDK（只需改 base_url + api_key），
    统一用 langchain-openai 的 ChatOpenAI 接入，仅切换参数。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── DeepSeek ──────────────────────────────────────────────────────────────
    deepseek_api_key: str = Field(default="", description="DeepSeek API Key")
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # 可用模型：
    #   deepseek-chat      → DeepSeek-V3，综合能力强，价格极低
    #   deepseek-reasoner  → DeepSeek-R1，推理能力最强（慢 3-5x，适合 Planner）
    deepseek_chat_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"

    # ── Qwen（阿里云百炼）────────────────────────────────────────────────────
    qwen_api_key: str = Field(default="", description="阿里云百炼 API Key")
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 可用模型：
    #   qwen-plus   → 均衡，性价比高
    #   qwen-turbo  → 最快最便宜
    #   qwen-max    → 最强，适合 Writer/Critic
    #   qwen-long   → 超长上下文（1M tokens）
    qwen_plus_model: str = "qwen-plus"
    qwen_turbo_model: str = "qwen-turbo"
    qwen_max_model: str = "qwen-max"
    qwen_long_model: str = "qwen-long"

    # ── OpenAI（可选）─────────────────────────────────────────────────────────
    openai_api_key: str = Field(default="", description="OpenAI API Key（可选）")
    openai_base_url: str | None = None

    # ── Anthropic（可选）──────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", description="Anthropic API Key（可选）")

    # ── 辅助工具 ──────────────────────────────────────────────────────────────
    cohere_api_key: str = Field(default="", description="Cohere Rerank API Key（可选）")
    cohere_rerank_model: str = "rerank-multilingual-v3.0"
    rerank_top_n: int = 5

    tavily_api_key: str = Field(default="", description="Tavily Web Search Key（可选）")
    llama_cloud_api_key: str = Field(default="", description="LlamaCloud PDF 解析 Key（可选）")

    # ── Agent 模型路由 ─────────────────────────────────────────────────────────
    # 格式：  "provider:model_name"
    # 默认：全部走 DeepSeek-V3（deepseek-chat），成本极低，效果好
    # 如果只有 Qwen，把所有 deepseek:deepseek-chat 改成 qwen:qwen-plus 即可
    # Critic 刻意用另一家评判，避免同源评判偏差
    planner_model_spec: str = "deepseek:deepseek-chat"
    writer_model_spec: str = "deepseek:deepseek-chat"
    analyst_model_spec: str = "deepseek:deepseek-chat"
    research_model_spec: str = "deepseek:deepseek-chat"
    critic_model_spec: str = "qwen:qwen-plus"

    # ── Embedding ──────────────────────────────────────────────────────────────
    # Qwen text-embedding-v3 免费额度充足，优先推荐
    # 若有 OpenAI Key 且想更高精度，改为 openai
    embedding_provider: str = "qwen"
    qwen_embedding_model: str = "text-embedding-v3"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1024  # qwen text-embedding-v3 维度

    # ── 通用参数 ───────────────────────────────────────────────────────────────
    default_temperature: float = 0.1
    max_tokens_planner: int = 2048
    max_tokens_writer: int = 4096
    max_tokens_default: int = 1024

    # ── Provider 可用性 ────────────────────────────────────────────────────────

    @property
    def has_deepseek(self) -> bool:
        return bool(self.deepseek_api_key and self.deepseek_api_key.startswith("sk-"))

    @property
    def has_qwen(self) -> bool:
        return bool(self.qwen_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.startswith("sk-"))

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.startswith("sk-ant"))

    @property
    def has_cohere(self) -> bool:
        return bool(self.cohere_api_key)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def has_llama_cloud(self) -> bool:
        return bool(self.llama_cloud_api_key)

    @property
    def available_providers(self) -> list[str]:
        p = []
        if self.has_deepseek:
            p.append("deepseek")
        if self.has_qwen:
            p.append("qwen")
        if self.has_openai:
            p.append("openai")
        if self.has_anthropic:
            p.append("anthropic")
        return p

    @property
    def primary_provider(self) -> str | None:
        return self.available_providers[0] if self.available_providers else None

    def parse_model_spec(self, spec: str) -> tuple[str, str]:
        """
        解析 "provider:model_name" 格式。
        若指定 provider 不可用，自动 fallback 到第一个可用 provider。
        返回 (provider, model_name)
        """
        if ":" not in spec:
            provider = self.primary_provider or "deepseek"
            return provider, spec

        provider, model = spec.split(":", 1)

        available_map = {
            "deepseek": self.has_deepseek,
            "qwen": self.has_qwen,
            "openai": self.has_openai,
            "anthropic": self.has_anthropic,
        }

        if not available_map.get(provider, False):
            fallback = self.primary_provider
            if not fallback:
                raise ValueError(
                    f"Provider '{provider}' 不可用，且没有任何可用 Provider。"
                    "请在 .env 中配置 DEEPSEEK_API_KEY 或 QWEN_API_KEY。"
                )
            fallback_default_models = {
                "deepseek": self.deepseek_chat_model,
                "qwen": self.qwen_plus_model,
                "openai": "gpt-4o",
                "anthropic": "claude-3-5-sonnet-20241022",
            }
            fallback_model = fallback_default_models[fallback]
            print(f"⚠️  Provider '{provider}' 不可用，自动降级到 {fallback}:{fallback_model}")
            return fallback, fallback_model

        return provider, model

    def get_llm_config(self, spec: str) -> dict:
        """
        根据 model spec 返回 ChatOpenAI(**config) 所需参数字典。
        DeepSeek / Qwen / OpenAI 均走 OpenAI 兼容接口。
        Anthropic 走独立 SDK，返回字典含 _provider 标识。
        """
        provider, model = self.parse_model_spec(spec)

        base: dict = {"temperature": self.default_temperature}

        if provider == "deepseek":
            return {
                **base,
                "model": model,
                "api_key": self.deepseek_api_key,
                "base_url": self.deepseek_base_url,
            }

        elif provider == "qwen":
            return {
                **base,
                "model": model,
                "api_key": self.qwen_api_key,
                "base_url": self.qwen_base_url,
            }

        elif provider == "openai":
            cfg = {**base, "model": model, "api_key": self.openai_api_key}
            if self.openai_base_url:
                cfg["base_url"] = self.openai_base_url
            return cfg

        elif provider == "anthropic":
            return {
                **base,
                "model": model,
                "api_key": self.anthropic_api_key,
                "_provider": "anthropic",
            }

        raise ValueError(f"未知 provider: {provider}")

    def get_embedding_config(self) -> dict:
        """
        返回 Embedding 初始化配置。
        优先顺序：显式配置的 embedding_provider → 可用的任意 provider → 报错
        """

        def _qwen_cfg() -> dict:
            return {
                "provider": "qwen",
                "model": self.qwen_embedding_model,
                "api_key": self.qwen_api_key,
                "base_url": self.qwen_base_url,
                "dimensions": self.embedding_dimensions,
            }

        def _openai_cfg() -> dict:
            return {
                "provider": "openai",
                "model": self.openai_embedding_model,
                "api_key": self.openai_api_key,
                "dimensions": 1536,
            }

        if self.embedding_provider == "openai" and self.has_openai:
            return _openai_cfg()
        if self.embedding_provider == "qwen" and self.has_qwen:
            return _qwen_cfg()
        if self.has_qwen:
            return _qwen_cfg()
        if self.has_openai:
            return _openai_cfg()

        raise ValueError("无法初始化 Embedding：请配置 QWEN_API_KEY 或 OPENAI_API_KEY。")


# ── 数据库配置 ────────────────────────────────────────────────────────────────


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "researchmind"
    postgres_password: str = "researchmind_dev"
    postgres_db: str = "researchmind"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_cache_ttl: int = 3600
    redis_session_ttl: int = 86400

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# ── 向量数据库配置 ────────────────────────────────────────────────────────────


class VectorDBSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: str = ""
    qdrant_collection: str = "knowledge_base"

    retrieval_top_k_dense: int = 20
    retrieval_top_k_sparse: int = 20
    retrieval_score_threshold: float = 0.5

    chunk_size: int = 512
    chunk_overlap: int = 64
    max_chunks_per_doc: int = 500

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


# ── Agent 配置 ────────────────────────────────────────────────────────────────


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    graph_recursion_limit: int = 30
    max_research_iterations: int = 5
    max_critic_iterations: int = 3
    max_parallel_research: int = 3
    task_timeout_seconds: int = 120
    hitl_timeout_seconds: int = 300
    hitl_enabled: bool = True
    max_tokens_per_task: int = 100_000
    max_cost_per_task_usd: float = 0.50
    min_quality_score: float = 0.75
    min_retrieval_coverage: float = 0.80
    checkpointer_backend: str = "postgres"


# ── 认证配置 ──────────────────────────────────────────────────────────────────


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    jwt_secret_key: str = Field(default="CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    jwt_refresh_token_expire_days: int = 30
    auth_disabled: bool = True
    rate_limit_per_minute: int = 100


# ── 可观测性配置 ──────────────────────────────────────────────────────────────


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "researchmind-pro"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "researchmind-backend"


# ── 主 Settings 类 ────────────────────────────────────────────────────────────


class Settings(
    AppSettings,
    LLMSettings,
    DatabaseSettings,
    VectorDBSettings,
    AgentSettings,
    AuthSettings,
    ObservabilitySettings,
):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def validate_startup(self) -> list[str]:
        """启动时配置检查，返回 warning 列表"""
        warnings: list[str] = []

        if not self.available_providers:
            warnings.append(
                "❌ 【严重】未配置任何 LLM API Key！请配置 DEEPSEEK_API_KEY 或 QWEN_API_KEY。"
            )
        if not self.has_cohere:
            warnings.append("⚠️  未配置 COHERE_API_KEY，Rerank 步骤将被跳过")
        if not self.has_tavily:
            warnings.append("⚠️  未配置 TAVILY_API_KEY，Web Search 工具将被禁用")
        if not self.langchain_tracing_v2:
            warnings.append("ℹ️  LANGCHAIN_TRACING_V2=false，Trace 不上传 LangSmith")
        if self.jwt_secret_key.startswith("CHANGE_ME") and self.is_production:
            warnings.append("❌ 【严重】生产环境不能使用默认 JWT_SECRET_KEY！")
        if self.auth_disabled and self.is_production:
            warnings.append("❌ 【严重】生产环境不能设置 AUTH_DISABLED=true！")

        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


if __name__ == "__main__":
    s = get_settings()

    print("=" * 55)
    print(f"  {s.app_name}  v{s.app_version}")
    print(f"  Environment : {s.environment.value}")
    print("=" * 55)

    print("\n📦 基础配置")
    print(f"  PostgreSQL : {s.postgres_host}:{s.postgres_port}/{s.postgres_db}")
    print(f"  Redis      : {s.redis_url}")
    print(f"  Qdrant     : {s.qdrant_url}")

    print("\n🤖 LLM Provider")
    print(f"  DeepSeek   : {'✅ 已配置' if s.has_deepseek else '── 未配置'}")
    print(f"  Qwen       : {'✅ 已配置' if s.has_qwen else '── 未配置'}")
    print(f"  OpenAI     : {'✅ 已配置' if s.has_openai else '── 未配置'}")
    print(f"  Anthropic  : {'✅ 已配置' if s.has_anthropic else '── 未配置'}")

    print("\n🛠️  辅助工具")
    print(f"  Cohere  Rerank : {'✅ 已配置' if s.has_cohere else '── 跳过 Rerank'}")
    print(f"  Tavily  Search : {'✅ 已配置' if s.has_tavily else '── 禁用 Web Search'}")
    print(f"  LlamaParse     : {'✅ 已配置' if s.has_llama_cloud else '── 基础 PDF 解析'}")

    print("\n🎯 Agent 模型路由")
    for agent, spec in [
        ("Planner", s.planner_model_spec),
        ("Writer", s.writer_model_spec),
        ("Analyst", s.analyst_model_spec),
        ("Research", s.research_model_spec),
        ("Critic", s.critic_model_spec),
    ]:
        try:
            provider, model = s.parse_model_spec(spec)
            print(f"  {agent:<10}: {provider:<10} → {model}")
        except ValueError as e:
            print(f"  {agent:<10}: ❌ {e}")

    print("\n📊 Embedding")
    try:
        emb = s.get_embedding_config()
        print(f"  {emb['provider']}  →  {emb['model']}  ({emb['dimensions']}d)")
    except ValueError as e:
        print(f"  ❌ {e}")

    print("\n⚠️  启动检查")
    warns = s.validate_startup()
    if warns:
        for w in warns:
            print(f"  {w}")
    else:
        print("  ✅ 全部通过")
    print()
