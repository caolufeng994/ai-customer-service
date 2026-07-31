"""
Application Configuration Module
Loads settings from environment variables and .env file
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "AI Customer Service"
    app_version: str = "1.0.0"
    debug: bool = True
    log_level: str = "INFO"
    
    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "ai_customer_service"
    db_user: str = "root"
    db_password: str = ""
    
    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    # JWT
    jwt_secret_key: str = "your-secret-key-change-this"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    
    # LLM
    llm_provider: str = "dashscope"  # dashscope or ollama
    dashscope_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    # DashScope 对话模型（较新推荐：qwen3.7-max / qwen3.7-plus / qwen3.7-flash）
    dashscope_model: str = "qwen3.7-plus"

    # Embedding
    embedding_provider: str = "dashscope"
    # 最新嵌入模型（2026 发布，1024 维，与 Chroma 维度兼容）
    embedding_model: str = "qwen3.7-text-embedding"
    local_embedding_model: str = "bge-small-zh-v1.5"
    
    # Vector Database
    chroma_persist_dir: str = "D:/data/chroma"
    
    # File storage (uploads)
    upload_dir: str = "D:/data/uploads"

    # Knowledge base initialization
    # 设为 true 时，服务启动会自动把 seed_docs 向量化（幂等，已入库的会跳过），
    # 实现题目要求的"初始化即可测问答"。默认 false，避免每次启动都触发网络 embedding。
    auto_init_kb: bool = False
    
    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    # Business Rules
    daily_quota_limit: int = 100
    max_question_length: int = 500
    retrieval_top_k: int = 8
    retrieval_threshold: float = 0.35
    max_history_rounds: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
