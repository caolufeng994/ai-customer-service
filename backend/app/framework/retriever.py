"""
Retriever Framework Primitive
Abstract base class and implementation for retrieval
Implements retrieval interface similar to LangChain BaseRetriever
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RetrievalNode:
    """Retrieval result node"""
    chunk_id: str
    content: str
    score: float
    doc_id: int
    doc_name: str
    chunk_index: int


class BaseRetriever(ABC):
    """
    Abstract base class for retrievers
    Retrieves relevant documents based on query
    """

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 8, **kwargs) -> List[RetrievalNode]:
        """
        Retrieve relevant documents

        Args:
            query: Search query
            top_k: Number of results to return
            **kwargs: Additional parameters

        Returns:
            List of retrieval nodes sorted by relevance
        """
        pass


class VectorRetriever(BaseRetriever):
    """
    Vector-based retriever using existing vector_store
    Wraps the existing app.rag.vector_store for framework compatibility
    """

    def __init__(self, top_k: int = 8, similarity_threshold: float = 0.6):
        """
        Initialize vector retriever

        Args:
            top_k: Number of results to retrieve
            similarity_threshold: Minimum similarity score
        """
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

        # Lazy import to avoid circular dependency
        from app.rag.vector_store import VectorStore
        from app.rag.embedder import Embedder

        self.vector_store = VectorStore()
        self.embedder = Embedder()

    def retrieve(self, query: str, top_k: Optional[int] = None, **kwargs) -> List[RetrievalNode]:
        """
        Retrieve using vector similarity search

        Args:
            query: Search query
            top_k: Number of results (uses instance default if None)
            **kwargs: Additional parameters (e.g., kb_id)

        Returns:
            List of retrieval nodes
        """
        top_k = top_k or self.top_k
        kb_id = kwargs.get("kb_id", "default")

        try:
            # Embed query
            query_embedding = self.embedder.embed(query)

            # Query vector store
            results = self.vector_store.query(
                query_embedding=query_embedding,
                n_results=top_k,
                where={"kb_id": kb_id} if kb_id else None
            )

            # Parse results
            nodes = []
            if results and results.get('ids') and results['ids'][0]:
                ids = results['ids'][0]
                documents = results['documents'][0] if results.get('documents') else []
                metadatas = results['metadatas'][0] if results.get('metadatas') else []
                distances = results['distances'][0] if results.get('distances') else []

                for chunk_id, doc, metadata, distance in zip(ids, documents, metadatas, distances):
                    similarity = 1.0 - distance  # Convert distance to similarity

                    if similarity < self.similarity_threshold:
                        continue

                    node = RetrievalNode(
                        chunk_id=chunk_id,
                        content=doc,
                        score=similarity,
                        doc_id=metadata.get('doc_id', 0),
                        doc_name=metadata.get('doc_name', ''),
                        chunk_index=metadata.get('chunk_index', 0)
                    )
                    nodes.append(node)

            logger.info(f"Retrieved {len(nodes)} nodes for query: {query[:50]}...")
            return nodes

        except Exception as e:
            logger.error(f"Vector retrieval failed: {e}")
            return []
