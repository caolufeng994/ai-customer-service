"""
Embedder Module
Handles text embedding with batch processing (DashScope cloud model)
"""
from typing import List, Optional
import logging
import time
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """
    Text embedder for converting text to vectors
    This step converts text chunks into embeddings for vector similarity search
    Supports batch processing for efficiency
    """
    
    def __init__(self, provider: str = None):
        """
        Initialize embedder
        
        Args:
            provider: Embedding provider (currently only 'dashscope'). Uses config default if None
        """
        self.provider = provider or settings.embedding_provider
        self.model = settings.embedding_model
        
        if self.provider == "dashscope":
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=30.0,
                max_retries=2
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider} (only 'dashscope' is supported)")
    
    def embed(self, text: str) -> List[float]:
        """
        Embed a single text
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector as list of floats
        """
        embeddings = self.embed_batch([text])
        return embeddings[0] if embeddings else []
    
    def embed_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        Embed multiple texts in batches
        
        Args:
            texts: List of input texts
            batch_size: Number of texts to process per batch
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        all_embeddings = []
        
        if self.provider == "dashscope":
            # DashScope 接口硬限制: 单次批量 embedding 最多 10 条(text-embedding-v3)。
            # 超出会返回 400 InvalidParameter "batch size is invalid"。这里无论调用方传入
            # 多大的 batch_size 都强制收敛到上限, 防止再次出现 FAQ 整篇上传失败。
            batch_size = min(batch_size, 10)
            # Cloud embedding with DashScope
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embeddings = None
                last_err: Optional[Exception] = None
                # 整批失败时在客户端 max_retries 之上再做一次指数退避重试,
                # 缓解偶发的网络抖动 / 限流(429),避免单个批次失败就让整篇
                # 文档被标记为 failed。
                for attempt in range(3):
                    try:
                        response = self.client.embeddings.create(
                            model=self.model,
                            input=batch,
                            dimensions=1024
                        )
                        batch_embeddings = [item.embedding for item in response.data]
                        break
                    except Exception as e:  # noqa: BLE001
                        last_err = e
                        logger.warning(
                            f"Embed batch {i // batch_size + 1} attempt "
                            f"{attempt + 1}/3 failed: {e}"
                        )
                        if attempt < 2:
                            time.sleep(2 ** attempt)  # 1s, 2s 退避
                if batch_embeddings is None:
                    logger.error(f"Failed to embed batch after retries: {last_err}")
                    raise RuntimeError(f"Embedding service unavailable: {last_err}")
                all_embeddings.extend(batch_embeddings)
                logger.debug(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider} (only 'dashscope' is supported)")
        
        return all_embeddings
    
    def get_dimension(self) -> int:
        """
        Get embedding dimension
        
        Returns:
            Dimension of the embedding vectors (DashScope text-embedding-v3 = 1024)
        """
        if self.provider == "dashscope":
            return 1024  # DashScope text-embedding-v3 is 1024 dimensions
        raise ValueError(f"Unsupported embedding provider: {self.provider} (only 'dashscope' is supported)")
    
    def retry_embed(self, text: str, max_retries: int = 3) -> List[float]:
        """
        Embed with retry logic
        
        Args:
            text: Input text
            max_retries: Maximum number of retry attempts
            
        Returns:
            Embedding vector
        """
        import time
        
        for attempt in range(max_retries):
            try:
                return self.embed(text)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Embedding failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Embedding failed after {max_retries} attempts: {e}")
                    raise
        
        return []
