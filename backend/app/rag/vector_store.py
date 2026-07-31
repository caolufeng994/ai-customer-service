"""
Vector Store Module
Handles vector database operations using Chroma
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Vector store for managing embeddings and similarity search
    This step handles storing and retrieving vectors using Chroma
    """
    
    def __init__(self, persist_dir: str = None):
        """
        Initialize vector store
        
        Args:
            persist_dir: Directory for persistent storage
        """
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection_name = "knowledge_base"
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """Get or create the Chroma collection"""
        try:
            collection = self.client.get_collection(
                name=self.collection_name,
                metadata={"description": "Knowledge base embeddings"}
            )
            logger.info(f"Loaded existing collection: {self.collection_name}")
        except:
            collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Knowledge base embeddings"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
        return collection
    
    def add_embeddings(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> None:
        """
        Add embeddings to the collection
        
        Args:
            embeddings: List of embedding vectors
            texts: List of original texts
            metadatas: List of metadata dictionaries
            ids: List of unique IDs for each embedding
        """
        try:
            self.collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(embeddings)} embeddings to vector store")
        except Exception as e:
            logger.error(f"Failed to add embeddings: {e}")
            raise
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 8,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Query the vector store for similar embeddings
        
        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            where: Metadata filter conditions
            
        Returns:
            Dictionary containing query results
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )
            return results
        except Exception as e:
            logger.error(f"Failed to query vector store: {e}")
            raise
    
    def delete_by_ids(self, ids: List[str]) -> None:
        """
        Delete embeddings by IDs
        
        Args:
            ids: List of embedding IDs to delete
        """
        try:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} embeddings from vector store")
        except Exception as e:
            logger.error(f"Failed to delete embeddings: {e}")
            raise
    
    def delete_by_metadata(self, metadata_filter: Dict[str, Any]) -> None:
        """
        Delete embeddings by metadata filter
        
        Args:
            metadata_filter: Metadata filter conditions
        """
        try:
            # Get all matching IDs first
            results = self.collection.get(
                where=metadata_filter,
                limit=10000  # Adjust based on expected document size
            )
            
            if results and results['ids']:
                self.delete_by_ids(results['ids'])
                logger.info(f"Deleted {len(results['ids'])} embeddings matching filter")
        except Exception as e:
            logger.error(f"Failed to delete by metadata: {e}")
            raise
    
    def get_count(self) -> int:
        """
        Get total number of embeddings in the collection
        
        Returns:
            Count of embeddings
        """
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Failed to get count: {e}")
            return 0
