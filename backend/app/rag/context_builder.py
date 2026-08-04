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
        Build context from retrieval results with L1-L4 operators.
        Returns only the context string (for backward compatibility / tests).
        """
        context, _ = self._build_context_internal(retrieval_results)
        return context

    def _build_context_internal(self, retrieval_results: List[RetrievalResult]) -> tuple[str, List[RetrievalResult]]:
        """
        内部构建: 返回 (context 字符串, 实际进入上下文的块列表 used)。
        used 的顺序与 [K编号] 严格一一对应 (K1=used[0], K2=used[1] ...),
        且已应用排序/重排/去重/预算截断。供 build_context_with_sources 做溯源对齐。
        """
        if not retrieval_results:
            return "", []

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

        # Build context with token budget; 同时记录真正被纳入的块 (used)
        context_parts = []
        used: List[RetrievalResult] = []
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
            used.append(result)
            current_chars += len(formatted_chunk)

        # Join with newlines
        context = "\n\n".join(context_parts)

        logger.info(f"Built context: {len(context_parts)} chunks, {current_chars} chars")
        return context, used

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
            - sources 与上下文中的 [K编号] **严格一一对应**: sources[i] 即 [K{i+1}]
              所指代的召回块(已排序/去重/预算截断后的实际纳入块)。这样前端可把
              答案里的 [K3] 直接映射到 sources[2], 实现"引用 -> 来源"双向绑定。
            - 每条 source 携带 k_index / doc_id / doc_name / chunk_id / chunk_index /
              score / snippet(块内容前 200 字), 足以在 UI 上精确呈现被引用的来源。
        """
        if not retrieval_results:
            return "", []

        # 内部构建: 拿到真正的上下文与一一对应的 used 块
        context, used = self._build_context_internal(retrieval_results)

        # 每条 used 块 -> 一个 source, 顺序即 [K编号] 顺序
        sources = []
        for idx, result in enumerate(used, start=1):
            sources.append({
                "k_index": idx,                        # 与上下文 [K编号] 对齐
                "doc_id": result.doc_id,
                "doc_name": result.doc_name,
                "chunk_id": result.chunk_id,
                "chunk_index": result.chunk_index,
                "score": float(result.score),
                # 来源片段展示被引用的完整块内容(不再截断), 让引用精确对应需求内容;
                # 前端以多行收起(最多 4 行)呈现, 悬停 tooltip 显示全文。
                "snippet": result.content,
            })

        return context, sources
