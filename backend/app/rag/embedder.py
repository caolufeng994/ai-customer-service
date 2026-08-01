"""
Embedder Module
Handles text embedding with batch processing
Supports both DashScope (cloud) and local models
"""
from typing import List
import logging
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
            provider: Embedding provider (dashscope or local). Uses config default if None
        """
        self.provider = provider or settings.embedding_provider
        self.model = settings.embedding_model if self.provider == "dashscope" else settings.local_embedding_model
        
        if self.provider == "dashscope":
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=30.0,
                max_retries=2
            )
        elif self.provider == "local":
            try:
                from sentence_transformers import SentenceTransformer
                self.model_instance = SentenceTransformer(self.model)
                logger.info(f"Loaded local embedding model: {self.model}")
            except ImportError:
                logger.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
                raise ImportError("sentence-transformers is required for local embedding")
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")
    
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
    
    def embed_batch(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
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
            # Cloud embedding with DashScope
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch,
                        dimensions=1024
                    )
                    embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(embeddings)
                    logger.debug(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")
                except Exception as e:
                    logger.error(f"Failed to embed batch: {e}")
                    raise RuntimeError(f"Embedding service unavailable: {e}")

        elif self.provider == "local":
            # Local embedding with sentence-transformers
            try:
                embeddings = self.model_instance.encode(
                    texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                all_embeddings = embeddings.tolist()
                logger.debug(f"Embedded {len(texts)} texts with local model")
            except Exception as e:
                logger.error(f"Failed to embed with local model: {e}")
                raise RuntimeError(f"Local embedding service unavailable: {e}")
        
        return all_embeddings
    
    def get_dimension(self) -> int:
        """
        Get embedding dimension
        
        Returns:
            Dimension of the embedding vectors
        """
        if self.provider == "dashscope":
            return 1024  # DashScope text-embedding-v3 is 1024 dimensions
        elif self.provider == "local":
            # Try to get dimension from model
            try:
                test_embedding = self.model_instance.encode("test")
                return len(test_embedding)
            except:
                return 768  # Common dimension for small models
        return 1024  # Default
    
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
