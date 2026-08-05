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

    # Embedding（仅支持 DashScope 云端向量模型，本地 local/bge 方案已移除）
    embedding_provider: str = "dashscope"  # 当前仅支持 dashscope
    # 真实可用的 DashScope 文本向量模型(默认输出 1024 维,与 Chroma 维度兼容)
    embedding_model: str = "text-embedding-v3"
    
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
    # 实现题目要求的"初始化即可测问答"。默认 true，确保 clone 后启动即可直接问答；
    # 若希望避免每次启动触发网络 embedding，可改为 false 并手动运行 backend/init_kb.py。
    auto_init_kb: bool = True
    
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

    # 文档切分策略:语义切分(替代固定长度递归切分)
    # 基于结构边界(标题/章节/段落)与主题转换点断块,仅对超长单元回退到按标点/字符切分。
    semantic_chunking: bool = True
    # 目标分块长度(软上限):尽量在语义边界处停,不超过此值。
    chunk_target_size: int = 500
    # 硬上限:任何分块不得超过该长度,超出部分走回退切分。须 >= chunk_target_size。
    max_chunk_size: int = 600
    # 回退切分时的块间重叠(仅超长单元回退时生效,语义合并阶段不引入重叠避免重复)。
    chunk_overlap: int = 80
    # 是否启用 embedding 主题转换点检测(更准,但每次入库额外产生 embedding 调用)。默认关闭。
    semantic_use_embedding: bool = False
    # embedding 模式下,相邻句相似度低于该值视为主题切换(断块)。
    semantic_topic_threshold: float = 0.5

    # Reranker Configuration
    # 默认开启 L1 重排（score fusion），提升大规模召回下的相关块排序质量；
    # 若 FlagEmbedding/bge-reranker-v2-m3 不可用，retriever 会自动降级为不重排（见 retriever.py）。
    enable_reranker: bool = True  # Enable reranking for better retrieval
    reranker_model: str = "BAAI/bge-reranker-v2-m3"  # Reranker model
    retrieval_recall_k: int = 20  # Recall top-k before reranking

    # Follow-up Suggestions
    enable_followup_suggestions: bool = True   # 启用追问引导：回答结束自动生成 2-3 个相关追问建议

    # Citation Verification (弱校验: 仅检查 [K编号] 是否在 1..N 范围, 不校验事实一致性)
    enable_citation_verification: bool = True  # Enable citation [K编号] range check

    # 防编造自检 (Faithfulness Gate)
    # 答案生成后, 用 LLM-as-Judge 比对"回答"与"召回上下文"的事实一致性,
    # 检测编造/矛盾/无关内容; 若不满足忠实度, 触发一次基于 [K] 内容的自我纠正并复检。
    # 该机制是真正的"防编造拦截", 区别于上面仅做编号范围校验的 citation_verification。
    enable_faithfulness_check: bool = True
    # 自检判定所用的采样温度(低温度=更稳定一致)
    faithfulness_temperature: float = 0.2
    # 自我纠正的最大次数(默认 1 次: 纠正一次后复检, 仍不通过则标记 grounded=False 放行)
    faithfulness_max_correct: int = 1

    # Agent 思维链(Chain-of-Thought)实时展示
    # 开启后,流式对话会在正式回答前先展示 agent 的"思考过程":
    # thinking_start(思考状态) -> thought(思维链内容流式输出) -> thinking_end(状态切换) -> 正式回答。
    # 思考阶段由一次轻量 LLM 推理调用驱动,失败会自动降级(跳过思考直接回答),不阻断主链路。
    enable_thinking_display: bool = True
    # 思维链生成的最大 token 数(控制思考长度,避免过长拖慢首字)。
    thinking_max_tokens: int = 350

    # 标准兜底话术(检索不到相关知识 / 兜底意图时直接返回, 不走 LLM, 零编造)
    fallback_message: str = "抱歉，我在知识库中未检索到与您问题相关的信息，暂时无法回答。如有需要，请联系人工客服。"

    # 管理员引导创建（首次启动自动建一个 admin 账号，幂等；已存在则跳过；生产可设 enabled=false 后手工管理）
    admin_bootstrap_enabled: bool = True
    admin_bootstrap_email: Optional[str] = None
    admin_bootstrap_phone: Optional[str] = None
    # 注意: 此默认值仅为占位符, 仅当 .env 未提供 ADMIN_BOOTSTRAP_PASSWORD 时生效。
    # 真实管理员密码必须写在 git 忽略的 .env 中, 切勿使用此占位符作为生产密码。
    admin_bootstrap_password: str = "Admin@ChangeMe123!"
    
    class Config:
        env_file = ".env"
        # Force UTF-8 when reading .env so Chinese comments don't crash on
        # Windows (default GBK/cp936) with "UnicodeDecodeError: 'gbk'".
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
