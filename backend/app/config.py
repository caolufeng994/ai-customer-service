"""
Application Configuration Module
Loads settings from environment variables and .env file
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""

    # Application
    app_name: str = "AI Customer Service"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "ai_customer_service"
    db_user: str = "root"
    db_password: str = Field(
        "",
        description="Database password. Empty = no-password root; OVERRIDE via .env in production",
    )

    @property
    def database_url(self) -> str:
        """拼装 SQLAlchemy 连接串（MySQL + PyMySQL 驱动），供 create_engine 使用。"""
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # JWT
    jwt_secret_key: str = Field(
        "dev-insecure-jwt-secret-change-me-in-prod-32",
        min_length=32,
        description="JWT secret key. Dev default; OVERRIDE via .env in production (min 32 chars)",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    
    # LLM
    llm_provider: str = "dashscope"  # currently only dashscope (cloud) is supported
    dashscope_api_key: str = ""
    # DashScope 对话模型(真实可用,免费额度覆盖): qwen-plus / qwen-max / qwen-turbo 等
    dashscope_model: str = "qwen-plus"

    # Embedding
    embedding_provider: str = "dashscope"
    # 真实可用的 DashScope 文本向量模型(默认输出 1024 维,与 Chroma 维度兼容)
    embedding_model: str = "text-embedding-v3"
    local_embedding_model: str = "bge-small-zh-v1.5"
    
    # Vector Database
    chroma_persist_dir: str = Field(
        default_factory=lambda: str(Path.cwd() / "data" / "chroma"),
        description="Chroma vector database persistence directory"
    )

    # File storage (uploads)
    upload_dir: str = Field(
        default_factory=lambda: str(Path.cwd() / "data" / "uploads"),
        description="File upload storage directory"
    )

    # Knowledge base initialization
    # 设为 true 时，服务启动会自动把 seed_docs 向量化（幂等，已入库的会跳过），
    # 实现题目要求的"初始化即可测问答"。默认 false，避免每次启动都触发网络 embedding。
    auto_init_kb: bool = False
    
    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """将逗号分隔的 CORS 来源字符串解析为列表，供 CORSMiddleware 使用。"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    # Business Rules
    daily_quota_limit: int = 100
    max_question_length: int = 500
    retrieval_top_k: int = 8
    # 相似度阈值。规范文档初版写 0.6，但实测 text-embedding-v3 的余弦相似度分布为：
    # 相关查询 0.55~0.74、无关查询 0.40~0.42。0.6 会误杀产品咨询等相关块(0.55~0.56)，
    # 0.35(原值)会让无关查询(0.40~0.42)漏入上下文。0.5 是该分布的干净分界点，
    # 既拦截无关 query 又保留相关召回。已同步更新 API文档.md 业务规则第5条。
    retrieval_threshold: float = 0.5
    # 检索降级阈值。None = 不做阈值降级（空结果直接走兜底提示），避免把无关内容
    # (实测 0.40~0.42) 重新漏入上下文。若需开启召回兜底，可设为 0.45(须高于无关带)。
    retrieval_fallback_threshold: Optional[float] = None
    max_history_rounds: int = 3

    # ---- 意图识别 / 策略路由（Agent 核心层）----
    # 是否启用意图识别与策略路由。开启后：知识类意图走 RAG 主链路，兜底/未知意图
    # 走无上下文兜底提示，从路由层杜绝无关内容注入（双保险，与阈值 0.5 互补）。
    enable_intent_routing: bool = True
    # 规则分类器置信度阈值：最佳意图加权分 >= 该值才采纳，否则归为「兜底闲聊」。
    # 关键词权重多 >=1.0，故 1.0 表示"至少命中一个有效关键词"。
    intent_confidence_threshold: float = 1.0
    # 规则分类低置信时是否调用 LLM 二次判定（默认关闭，保持零额外 LLM 调用与成本控制）。
    intent_fallback_to_llm: bool = False

    # Rate Limiting
    global_rate_limit: str = "100/minute"  # Global RPS limit
    ip_rate_limit: str = "30/minute"  # Per-IP RPS limit

    # Reranker Configuration
    enable_reranker: bool = False  # Enable reranking for better retrieval
    reranker_model: str = "BAAI/bge-reranker-v2-m3"  # Reranker model
    retrieval_recall_k: int = 20  # Recall top-k before reranking

    # Follow-up Suggestions
    enable_followup_suggestions: bool = False  # Enable follow-up question suggestions

    # Citation Verification
    enable_citation_verification: bool = True  # Enable citation verification to prevent hallucinations
    
    class Config:
        env_file = ".env"
        # Force UTF-8 when reading .env so Chinese comments don't crash on
        # Windows (default GBK/cp936) with "UnicodeDecodeError: 'gbk'".
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
