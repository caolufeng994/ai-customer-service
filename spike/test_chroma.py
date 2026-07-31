"""
Spike test for Chroma vector database
Purpose: Verify Chroma can persist, store, and retrieve vectors with metadata
"""
import chromadb
from chromadb.config import Settings
import numpy as np

def test_chroma_basic():
    """Test basic Chroma operations"""
    try:
        # Initialize Chroma with persistent storage
        client = chromadb.PersistentClient(path="./data/chroma_test")
        
        # Create or get collection
        collection = client.get_or_create_collection(
            name="test_collection",
            metadata={"description": "Spike test collection"}
        )
        
        print(f"✓ Chroma client initialized")
        print(f"Collection count: {collection.count()}")
        
        # Add some test documents
        test_docs = [
            "退换货政策：7天内无理由退货",
            "产品价格：基础版99元，专业版199元",
            "客服时间：周一至周五 9:00-18:00"
        ]
        
        # Generate dummy embeddings (1024 dims)
        embeddings = [np.random.rand(1024).tolist() for _ in test_docs]
        
        # Insert with metadata
        collection.add(
            documents=test_docs,
            embeddings=embeddings,
            metadatas=[
                {"doc_id": "doc_1", "chunk_index": 0, "category": "policy"},
                {"doc_id": "doc_2", "chunk_index": 0, "category": "pricing"},
                {"doc_id": "doc_3", "chunk_index": 0, "category": "service"}
            ],
            ids=["chunk_1", "chunk_2", "chunk_3"]
        )
        
        print(f"✓ Added {len(test_docs)} documents")
        print(f"Collection count after add: {collection.count()}")
        
        return True, client, collection
        
    except Exception as e:
        print(f"✗ Chroma Basic Test Failed: {e}")
        return False, None, None

def test_chroma_query(client, collection):
    """Test Chroma query with metadata filtering"""
    try:
        # Query with dummy embedding
        query_embedding = np.random.rand(1024).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=2,
            where={"category": "policy"}
        )
        
        print(f"✓ Query Test Passed")
        print(f"Results returned: {len(results['ids'][0])}")
        print(f"Matched documents: {results['documents'][0]}")
        
        return True
        
    except Exception as e:
        print(f"✗ Chroma Query Test Failed: {e}")
        return False

def test_chroma_delete(client, collection):
    """Test Chroma delete operation"""
    try:
        # Delete a specific chunk
        collection.delete(ids=["chunk_1"])
        
        print(f"✓ Delete Test Passed")
        print(f"Collection count after delete: {collection.count()}")
        
        # Verify deletion
        results = collection.get(ids=["chunk_1"])
        print(f"Deleted chunk retrieval: {results}")
        
        return True
        
    except Exception as e:
        print(f"✗ Chroma Delete Test Failed: {e}")
        return False

def test_chroma_metadata_filter(client, collection):
    """Test complex metadata filtering"""
    try:
        # Query with multiple metadata conditions
        query_embedding = np.random.rand(1024).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"doc_id": {"$in": ["doc_2", "doc_3"]}}
        )
        
        print(f"✓ Metadata Filter Test Passed")
        print(f"Filtered results: {len(results['ids'][0])} chunks")
        
        return True
        
    except Exception as e:
        print(f"✗ Metadata Filter Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Chroma Vector Database Spike Test")
    print("=" * 60)
    
    success, client, collection = test_chroma_basic()
    
    if success:
        print()
        test_chroma_query(client, collection)
        print()
        test_chroma_delete(client, collection)
        print()
        test_chroma_metadata_filter(client, collection)
        print()
        print("✓ All Chroma tests completed")
