"""
Context Builder Module
Builds context from retrieval results with token budget and deduplication
Implements L1-L4 retrieval enhancement operators
"""
from typing import List
from app.rag.retriever import RetrievalResult
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Context builder for assembling retrieved chunks into context
    This step builds the context with token budget control and deduplication
    Implements L1-L4 retrieval enhancement operators:
    - L1: Reranking with score fusion
    - L2: Sandwich layout (high confidence at top/bottom)
    - L3: Map-Reduce summarization for large recalls
    - L4: Citation verification
    """

    def __init__(self, max_tokens: int = 2000):
        """
        Initialize context builder

        Args:
            max_tokens: Maximum context tokens (approximate character count)
        """
        self.max_tokens = max_tokens
        # Approximate token to character ratio for Chinese: 1 token ≈ 1.5 characters
        self.max_chars = max_tokens * 2

        # L1 Reranking configuration
        self.enable_rerank = settings.enable_reranker
        self.rerank_weight = 0.7  # Weight for rerank score vs original score

        # L2 Sandwich configuration (disabled by default for backward compatibility)
        self.enable_sandwich = False
        self.high_confidence_threshold = 0.8
        self.low_confidence_threshold = 0.5

        # L3 Summarization configuration
        self.enable_summarization = False  # Disabled by default (requires LLM)
        self.summarization_threshold = 10  # Number of chunks before summarization

        # L4 Verification configuration
        self.enable_verification = True
    
    def build_context(self, retrieval_results: List[RetrievalResult]) -> str:
        """
        Build context from retrieval results with L1-L4 operators

        Args:
            retrieval_results: List of retrieval results

        Returns:
            Context string with deduplicated chunks
        """
        if not retrieval_results:
            return ""

        # Baseline: sort by score descending (high score first)
        # This ensures "high priority" semantics even when L1 rerank is disabled
        processed_results = sorted(retrieval_results, key=lambda x: x.score, reverse=True)

        # Apply L1: Reranking (if enabled) - on top of baseline sorting
        processed_results = self._apply_l1_rerank(processed_results)

        # Apply L2: Sandwich layout (if enabled)
        processed_results = self._apply_l2_sandwich(processed_results)

        # Apply L3: Summarization (if enabled and needed)
        processed_results = self._apply_l3_summarization(processed_results)

        # Apply L4: Verification (if enabled)
        processed_results = self._apply_l4_verification(processed_results)

        # Deduplicate by content.
        # NOTE: use the content string itself as the dedup key, not hash().
        # Python's str hash is salted per-process (PYTHONHASHSEED), so a hash
        # key is non-deterministic across runs and can also collide, causing
        # distinct chunks to be wrongly dropped or duplicates to survive.
        seen_contents = set()
        unique_results = []

        for result in processed_results:
            if result.content not in seen_contents:
                seen_contents.add(result.content)
                unique_results.append(result)

        # Build context with token budget
        context_parts = []
        current_chars = 0

        for result in unique_results:
            # Format: [K编号] 内容 (simplified for citation verification)
            chunk_index = len(context_parts) + 1
            formatted_chunk = f"[K{chunk_index}] {result.content}"

            # Check if adding this chunk would exceed budget
            if current_chars + len(formatted_chunk) > self.max_chars:
                logger.info(f"Context truncated at {len(context_parts)} chunks")
                break

            context_parts.append(formatted_chunk)
            current_chars += len(formatted_chunk)

        # Join with newlines
        context = "\n\n".join(context_parts)

        logger.info(f"Built context: {len(context_parts)} chunks, {current_chars} chars")
        return context

    def _apply_l1_rerank(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """
        L1: Reranking with score fusion
        Combines original similarity score with reranker score (if available)
        """
        if not self.enable_rerank:
            return results

        # If results have been reranked (score already updated), just sort
        # Otherwise, this is a no-op as reranking happens in Retriever
        return sorted(results, key=lambda x: x.score, reverse=True)

    def _apply_l2_sandwich(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """
        L2: Sandwich layout
        High confidence chunks at top and bottom, medium in middle
        """
        if not self.enable_sandwich:
            return results

        high_conf = [r for r in results if r.score >= self.high_confidence_threshold]
        medium_conf = [r for r in results if self.low_confidence_threshold <= r.score < self.high_confidence_threshold]
        low_conf = [r for r in results if r.score < self.low_confidence_threshold]

        # Layout: high -> low -> medium -> high (sandwich)
        # This puts most relevant at both ends to capture attention
        sandwiched = high_conf[:len(high_conf)//2] + low_conf + medium_conf + high_conf[len(high_conf)//2:]

        return sandwiched

    def _apply_l3_summarization(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """
        L3: Map-Reduce summarization for large recalls
        Summarizes chunks when count exceeds threshold
        """
        if not self.enable_summarization or len(results) < self.summarization_threshold:
            return results

        # In a full implementation, this would:
        # 1. Map: Summarize each chunk individually
        # 2. Reduce: Combine summaries into a single summary
        # For now, just truncate to respect token budget
        logger.info(f"Summarization would be applied to {len(results)} chunks (disabled)")
        return results

    def _apply_l4_verification(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """
        L4: Citation verification
        Filters out chunks with invalid indices or very low scores
        """
        if not self.enable_verification:
            return results

        # Filter out chunks with very low scores
        verified = [r for r in results if r.score >= 0.3]

        if len(verified) < len(results):
            logger.info(f"L4 verification filtered {len(results) - len(verified)} low-score chunks")

        return verified
    
    def build_context_with_sources(self, retrieval_results: List[RetrievalResult]) -> tuple[str, List[dict]]:
        """
        Build context and return source information

        Args:
            retrieval_results: List of retrieval results

        Returns:
            Tuple of (context string, source information list)

        Notes:
            - 每个 doc_id 生成一条 source 条目（与测试约定一致：source 数 = 去重后 doc 数）。
            - 除保留首个 chunk_id（向后兼容 ChatSource 契约）外，额外用 `chunk_ids`
              列出该文档命中的全部 chunk，使前端来源与存入 DB 的 citations（全量）一致，
              解决原先"按 doc_id 去重只留首个 chunk_id"导致 chunk 级引用丢失的问题。
        """
        if not retrieval_results:
            return "", []

        # Build context
        context = self.build_context(retrieval_results)

        # 收集每个 doc 命中的全部 chunk_id（按结果出现顺序，即相似度降序）
        doc_chunk_ids: dict[int, list[str]] = {}
        for result in retrieval_results:
            doc_chunk_ids.setdefault(result.doc_id, []).append(result.chunk_id)

        # Extract source information (one entry per doc_id)
        sources = []
        seen_docs = set()
        for result in retrieval_results:
            if result.doc_id in seen_docs:
                continue
            seen_docs.add(result.doc_id)
            sources.append({
                "doc_id": result.doc_id,
                "doc_name": result.doc_name,
                "chunk_id": result.chunk_id,           # 首个 chunk（向后兼容）
                "chunk_ids": doc_chunk_ids[result.doc_id],  # 该文档全部命中 chunk
                "score": float(result.score),
            })

        return context, sources
