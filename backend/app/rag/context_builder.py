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
        """
        if not retrieval_results:
            return "", []
        
        # Build context
        context = self.build_context(retrieval_results)
        
        # Extract source information
        sources = []
        seen_docs = set()
        
        for result in retrieval_results:
            if result.doc_id not in seen_docs:
                sources.append({
                    "doc_id": result.doc_id,
                    "doc_name": result.doc_name,
                    "chunk_id": result.chunk_id,
                    "score": float(result.score)
                })
                seen_docs.add(result.doc_id)
        
        return context, sources
