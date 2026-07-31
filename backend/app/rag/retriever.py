"""
Retriever Module
Handles similarity search with Top-K and similarity threshold
"""
from typing import List, Dict, Any, Optional
from app.rag.vector_store import VectorStore
from app.rag.embedder import Embedder
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
    
    def retrieve(self, query: str, kb_id: str = "default") -> List[RetrievalResult]:
        """
        Retrieve relevant chunks for a query
        
        Args:
            query: User query text
            kb_id: Knowledge base ID to filter
            
        Returns:
            List of retrieval results sorted by similarity
        """
        # Step 1: Embed the query
        try:
            query_embedding = self.embedder.embed(query)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return []
        
        # Step 2: Query vector store
        try:
            results = self.vector_store.query(
                query_embedding=query_embedding,
                n_results=self.top_k,
                where={"kb_id": kb_id} if kb_id else None
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
        
        logger.info(f"Retrieved {len(retrieval_results)} chunks (threshold: {self.similarity_threshold})")
        return retrieval_results
    
    def retrieve_with_fallback(self, query: str, kb_id: str = "default") -> List[RetrievalResult]:
        """
        Retrieve with fallback to lower threshold if no results
        
        Args:
            query: User query text
            kb_id: Knowledge base ID to filter
            
        Returns:
            List of retrieval results
        """
        results = self.retrieve(query, kb_id)
        
        # If no results, try with lower threshold
        if not results and self.similarity_threshold > 0.3:
            logger.info("No results with threshold, trying lower threshold")
            original_threshold = self.similarity_threshold
            self.similarity_threshold = 0.3
            results = self.retrieve(query, kb_id)
            self.similarity_threshold = original_threshold
        
        return results
