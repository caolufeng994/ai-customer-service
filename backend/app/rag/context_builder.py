"""
Context Builder Module
Builds context from retrieval results with token budget and deduplication
"""
from typing import List
from app.rag.retriever import RetrievalResult
import logging

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Context builder for assembling retrieved chunks into context
    This step builds the context with token budget control and deduplication
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
    
    def build_context(self, retrieval_results: List[RetrievalResult]) -> str:
        """
        Build context from retrieval results
        
        Args:
            retrieval_results: List of retrieval results
            
        Returns:
            Context string with deduplicated chunks
        """
        if not retrieval_results:
            return ""
        
        # Step 1: Sort by score (already sorted, but ensure)
        sorted_results = sorted(retrieval_results, key=lambda x: x.score, reverse=True)
        
        # Step 2: Deduplicate by content
        seen_contents = set()
        unique_results = []
        
        for result in sorted_results:
            # Simple deduplication by content hash
            content_hash = hash(result.content)
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_results.append(result)
        
        # Step 3: Build context with token budget
        context_parts = []
        current_chars = 0
        
        for result in unique_results:
            # Format: [文档名] 内容
            formatted_chunk = f"[{result.doc_name}] {result.content}"
            
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
