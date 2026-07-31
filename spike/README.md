# Spike Tests - External Dependencies Verification

This directory contains spike tests to verify external dependencies before full development.

## Purpose

These tests validate that all external APIs and services are accessible and working correctly:
- **LLM API** (DashScope qwen-plus) - Chat and streaming functionality
- **Embedding API** (DashScope text-embedding-v3) - Vector generation
- **ChromaDB** - Local vector database persistence and retrieval

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variable for DashScope API key:
```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY="your-api-key-here"

# Linux/Mac
export DASHSCOPE_API_KEY="your-api-key-here"
```

## Running Tests

Run each test individually:

```bash
# Test LLM connectivity
python test_llm.py

# Test Embedding API
python test_embedding.py

# Test ChromaDB
python test_chroma.py
```

## Expected Results

All tests should show ✓ (checkmark) indicating success. If any test fails with ✗, investigate the error before proceeding with main development.

## Notes

- ChromaDB will create a `./data/chroma_test` directory for persistent storage
- These are minimal spike tests - not production code
- If DashScope fails, fallback to Ollama local model as per execution plan
