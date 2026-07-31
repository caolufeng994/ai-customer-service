"""
Spike test for Embedding connectivity (DashScope text-embedding-v3)
Purpose: Verify embedding API works and can generate vectors
"""
import os
from openai import OpenAI

# Load API key from environment or use placeholder
API_KEY = os.getenv("DASHSCOPE_API_KEY", "your-api-key-here")

def test_embedding():
    """Test text embedding generation"""
    try:
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        test_texts = [
            "这是一个测试文本",
            "退换货政策是什么",
            "产品价格查询"
        ]
        
        response = client.embeddings.create(
            model="text-embedding-v3",
            input=test_texts,
            dimensions=1024
        )
        
        print(f"✓ Embedding Test Passed")
        print(f"Model: {response.model}")
        print(f"Embeddings generated: {len(response.data)}")
        print(f"Vector dimension: {len(response.data[0].embedding)}")
        print(f"Sample vector (first 5 dims): {response.data[0].embedding[:5]}")
        
        # Test similarity calculation
        import numpy as np
        vec1 = np.array(response.data[0].embedding)
        vec2 = np.array(response.data[1].embedding)
        similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        print(f"Cosine similarity between text 1 and 2: {similarity:.4f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Embedding Test Failed: {e}")
        return False

def test_batch_embedding():
    """Test batch embedding with larger dataset"""
    try:
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        # Simulate a batch of chunks
        chunks = [f"这是第{i}个文本片段，用于测试批量向量化功能" for i in range(20)]
        
        response = client.embeddings.create(
            model="text-embedding-v3",
            input=chunks,
            dimensions=1024
        )
        
        print(f"✓ Batch Embedding Test Passed")
        print(f"Batch size: {len(chunks)}")
        print(f"Successfully embedded: {len(response.data)} vectors")
        
        return True
        
    except Exception as e:
        print(f"✗ Batch Embedding Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Embedding Connectivity Spike Test")
    print("=" * 60)
    
    if API_KEY == "your-api-key-here":
        print("⚠ Warning: Using placeholder API key. Set DASHSCOPE_API_KEY environment variable.")
    
    test_embedding()
    print()
    test_batch_embedding()
