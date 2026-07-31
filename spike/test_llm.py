"""
Spike test for LLM connectivity (DashScope qwen-plus)
Purpose: Verify LLM API key works and basic chat functionality
"""
import os
from openai import OpenAI

# Load API key from environment or use placeholder
API_KEY = os.getenv("DASHSCOPE_API_KEY", "your-api-key-here")

def test_llm_chat():
    """Test basic chat completion with DashScope"""
    try:
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, please respond with 'LLM connection successful'"}
            ],
            temperature=0.7
        )
        
        result = response.choices[0].message.content
        print(f"✓ LLM Chat Test Passed")
        print(f"Response: {result}")
        return True
        
    except Exception as e:
        print(f"✗ LLM Chat Test Failed: {e}")
        return False

def test_llm_stream():
    """Test streaming chat completion"""
    try:
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        print("✓ LLM Stream Test Started")
        stream = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "user", "content": "Count from 1 to 5"}
            ],
            stream=True
        )
        
        chunks = []
        for chunk in stream:
            if chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)
                print(chunk.choices[0].delta.content, end="", flush=True)
        
        print("\n✓ LLM Stream Test Passed")
        return True
        
    except Exception as e:
        print(f"✗ LLM Stream Test Failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("LLM Connectivity Spike Test")
    print("=" * 60)
    
    if API_KEY == "your-api-key-here":
        print("⚠ Warning: Using placeholder API key. Set DASHSCOPE_API_KEY environment variable.")
    
    test_llm_chat()
    print()
    test_llm_stream()
