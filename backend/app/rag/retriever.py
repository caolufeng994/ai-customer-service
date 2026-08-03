"""
Retriever Module
Handles similarity search with Top-K and similarity threshold
Supports optional reranking for better retrieval quality
"""
from typing import List, Dict, Any, Optional
from app.rag.vector_store import VectorStore
from app.rag.embedder import Embedder
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RetrievalResult:
    """Single retrieval result"""
    def __init__(
        self,
        chunk_id: str,
        content: str,
        score: float,
        doc_id: int,
        doc_name: str,
        chunk_index: int
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.score = score
        self.doc_id = doc_id
        self.doc_name = doc_name
        self.chunk_index = chunk_index
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": float(self.score),
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "chunk_index": self.chunk_index
        }


class Retriever:
    """
    Retriever for finding relevant chunks from vector store
    This step retrieves similar chunks based on query embedding
    Supports optional reranking for better retrieval quality
    """

    def __init__(
        self,
        top_k: int = 8,
        similarity_threshold: float = 0.6,
        embedder: Optional[Embedder] = None
    ):
        """
        Initialize retriever

        Args:
            top_k: Number of top results to retrieve
            similarity_threshold: Minimum similarity score (0-1)
            embedder: Embedder instance (creates new if None)
        """
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.embedder = embedder or Embedder()
        self.vector_store = VectorStore()
        self.reranker = None

        # Initialize reranker if enabled
        if settings.enable_reranker:
            try:
                from FlagEmbedding import BGEM3FlagModel
                logger.info(f"Loading reranker model: {settings.reranker_model}")
                self.reranker = BGEM3FlagModel(settings.reranker_model, use_fp16=True)
            except ImportError:
                logger.warning("FlagEmbedding not installed, reranking disabled")
                settings.enable_reranker = False
            except Exception as e:
                logger.error(f"Failed to load reranker model: {e}")
                settings.enable_reranker = False
    
    def retrieve(self, query: str, kb_id: str = "default", user_id: Optional[int] = None) -> List[RetrievalResult]:
        """
        Retrieve relevant chunks for a query

        Args:
            query: User query text
            kb_id: Knowledge base ID to filter
            user_id: 可选按文档归属用户过滤（多租户隔离增强，默认 None=不过滤，
                     保持单租户共享 KB 的现有行为）。

        Returns:
            List of retrieval results sorted by similarity
        """
        # Determine recall_k for initial retrieval
        recall_k = settings.retrieval_recall_k if settings.enable_reranker else self.top_k

        # Step 1: Embed the query
        try:
            query_embedding = self.embedder.embed(query)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return []

        # Step 2: Query vector store with recall_k
        try:
            results = self.vector_store.query(
                query_embedding=query_embedding,
                n_results=recall_k,
                where={"kb_id": kb_id} if kb_id else None,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(f"Failed to query vector store: {e}")
            return []

        # Step 3: Parse and filter results
        retrieval_results = []

        if not results or not results.get('ids') or not results['ids'][0]:
            logger.warning("No results found in vector store")
            return []

        ids = results['ids'][0]
        documents = results['documents'][0] if results.get('documents') else []
        metadatas = results['metadatas'][0] if results.get('metadatas') else []
        distances = results['distances'][0] if results.get('distances') else []

        # Convert distance to similarity score (cosine distance to similarity)
        for i, (chunk_id, doc, metadata, distance) in enumerate(zip(ids, documents, metadatas, distances)):
            # Cosine distance to similarity: similarity = 1 - distance
            similarity = 1.0 - distance

            # Filter by similarity threshold
            if similarity < self.similarity_threshold:
                continue

            result = RetrievalResult(
                chunk_id=chunk_id,
                content=doc,
                score=similarity,
                doc_id=metadata.get('doc_id', 0),
                doc_name=metadata.get('doc_name', ''),
                chunk_index=metadata.get('chunk_index', 0)
            )
            retrieval_results.append(result)

        # Step 4: Rerank if enabled
        if settings.enable_reranker and self.reranker and len(retrieval_results) > self.top_k:
            retrieval_results = self._rerank(query, retrieval_results)

        # Step 5: Return top_k results
        final_results = retrieval_results[:self.top_k]
        logger.info(f"Retrieved {len(final_results)} chunks (threshold: {self.similarity_threshold}, reranked: {settings.enable_reranker})")
        return final_results

    def _rerank(self, query: str, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """
        Rerank retrieval results using cross-encoder

        Args:
            query: User query text
            results: Initial retrieval results

        Returns:
            Reranked results
        """
        try:
            # Prepare inputs for reranker
            passages = [result.content for result in results]

            # Compute reranking scores
            rerank_scores = self.reranker.compute_score(
                [[query, passage] for passage in passages],
                max_length_in_batch=512
            )

            # Update scores and resort
            for i, result in enumerate(results):
                result.score = float(rerank_scores[i])

            # Sort by rerank score (descending)
            results.sort(key=lambda x: x.score, reverse=True)

            logger.info(f"Reranked {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Reranking failed, using original order: {e}")
            return results
    
    def retrieve_with_fallback(self, query: str, kb_id: str = "default", user_id: Optional[int] = None) -> List[RetrievalResult]:
        """
        Retrieve with optional recall fallback.

        默认不做阈值降级：若主阈值（retrieval_threshold，推荐 0.5）下无结果，
        直接返回空，由上层走「无上下文兜底提示」。这避免了旧实现把阈值降到 0.3
        后，将无关内容（实测相似度 0.40~0.42）重新漏入 LLM 上下文的安全隐患。

        如需开启召回兜底，可在配置中设置 `retrieval_fallback_threshold`（须高于
        无关内容带，建议 >= 0.45），仅在空结果且下限低于主阈值时按受限下限再检索一次。

        Args:
            query: User query text
            kb_id: Knowledge base ID to filter

        Returns:
            List of retrieval results
        """
        results = self.retrieve(query, kb_id, user_id=user_id)

        # 仅当显式配置且下限低于主阈值时，才以受限下限再检索一次（默认 None => 不降级）。
        fb = settings.retrieval_fallback_threshold
        if not results and fb is not None and fb < self.similarity_threshold:
            logger.info(f"No results at threshold {self.similarity_threshold}, trying floor {fb}")
            original_threshold = self.similarity_threshold
            self.similarity_threshold = fb
            try:
                results = self.retrieve(query, kb_id, user_id=user_id)
            finally:
                self.similarity_threshold = original_threshold

        return results
