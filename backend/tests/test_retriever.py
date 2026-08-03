"""
Unit tests for Retriever module
Tests threshold filtering, fallback, and retrieval logic
"""
import pytest
from unittest.mock import Mock, patch
from app.rag.retriever import Retriever, RetrievalResult
from app.rag.embedder import Embedder
from app.rag.vector_store import VectorStore


@pytest.fixture
def mock_embedder():
    """Mock embedder instance"""
    embedder = Mock(spec=Embedder)
    embedder.embed.return_value = [0.1] * 1024  # Mock embedding vector
    return embedder


@pytest.fixture
def mock_vector_store():
    """Mock vector store instance"""
    vector_store = Mock(spec=VectorStore)
    return vector_store


@pytest.fixture
def retriever(mock_embedder, mock_vector_store):
    """Create retriever instance with mocked dependencies"""
    with patch('app.rag.retriever.settings.enable_reranker', False):
        retriever = Retriever(top_k=8, similarity_threshold=0.6, embedder=mock_embedder)
        retriever.vector_store = mock_vector_store
        return retriever


class TestRetriever:
    """Test cases for Retriever class"""

    def test_retrieve_success(self, retriever, mock_vector_store):
        """Test successful retrieval with valid results"""
        # Mock vector store response
        mock_vector_store.query.return_value = {
            'ids': [['chunk1', 'chunk2', 'chunk3']],
            'documents': [['Content 1', 'Content 2', 'Content 3']],
            'metadatas': [[
                {'doc_id': 1, 'doc_name': 'doc1.pdf', 'chunk_index': 0},
                {'doc_id': 1, 'doc_name': 'doc1.pdf', 'chunk_index': 1},
                {'doc_id': 2, 'doc_name': 'doc2.pdf', 'chunk_index': 0}
            ]],
            'distances': [[0.1, 0.2, 0.3]]  # High similarity (low distance)
        }

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 3
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert results[0].score == 0.9  # 1 - 0.1
        assert results[1].score == 0.8  # 1 - 0.2
        assert results[2].score == 0.7  # 1 - 0.3

    def test_retrieve_threshold_filtering(self, retriever, mock_vector_store):
        """Test that results below similarity threshold are filtered.

        similarity = 1 - distance; threshold = 0.6 -> keep distance <= 0.4.
        distances [0.1, 0.3, 0.8] -> similarities [0.9, 0.7, 0.2] -> 2 kept.
        """
        mock_vector_store.query.return_value = {
            'ids': [['chunk1', 'chunk2', 'chunk3']],
            'documents': [['Content 1', 'Content 2', 'Content 3']],
            'metadatas': [[
                {'doc_id': 1, 'doc_name': 'doc1.pdf', 'chunk_index': 0},
                {'doc_id': 1, 'doc_name': 'doc1.pdf', 'chunk_index': 1},
                {'doc_id': 2, 'doc_name': 'doc2.pdf', 'chunk_index': 0}
            ]],
            'distances': [[0.1, 0.3, 0.8]]
        }

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 2  # Only first two pass threshold
        assert results[0].score == 0.9
        assert results[1].score == 0.7

    def test_retrieve_empty_results(self, retriever, mock_vector_store):
        """Test handling of empty vector store results"""
        mock_vector_store.query.return_value = {
            'ids': [[]],
            'documents': [[]],
            'metadatas': [[]],
            'distances': [[]]
        }

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 0

    def test_retrieve_embedding_failure(self, retriever, mock_embedder):
        """Test handling of embedding failure"""
        mock_embedder.embed.side_effect = Exception("Embedding failed")

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 0

    def test_retrieve_vector_store_failure(self, retriever, mock_vector_store):
        """Test handling of vector store query failure"""
        mock_vector_store.query.side_effect = Exception("Query failed")

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 0

    def test_retrieve_with_fallback_success(self, retriever, mock_vector_store):
        """Test fallback mechanism when no results with initial threshold"""
        # First call: no results with high threshold
        mock_vector_store.query.return_value = {
            'ids': [[]],
            'documents': [[]],
            'metadatas': [[]],
            'distances': [[]]
        }

        results = retriever.retrieve_with_fallback("test query", kb_id="default")

        # Should try lower threshold
        assert mock_vector_store.query.call_count == 2

    def test_retrieve_top_k_limit(self, retriever, mock_vector_store):
        """Test that only top_k results are returned.

        All 10 mock chunks are high similarity (distance <= 0.4 -> similarity >= 0.6),
        so none are dropped by the threshold filter; top_k=8 then caps the list.
        """
        mock_vector_store.query.return_value = {
            'ids': [['chunk1', 'chunk2', 'chunk3', 'chunk4', 'chunk5', 'chunk6', 'chunk7', 'chunk8', 'chunk9', 'chunk10']],
            'documents': [['Content ' + str(i) for i in range(1, 11)]],
            'metadatas': [[
                {'doc_id': 1, 'doc_name': 'doc1.pdf', 'chunk_index': i}
                for i in range(10)
            ]],
            'distances': [[0.04 * i for i in range(1, 11)]]  # 0.04..0.40 -> all >= 0.6 sim
        }

        results = retriever.retrieve("test query", kb_id="default")

        assert len(results) == 8  # top_k = 8

    def test_retrieval_result_to_dict(self):
        """Test RetrievalResult to_dict method"""
        result = RetrievalResult(
            chunk_id="chunk1",
            content="Test content",
            score=0.85,
            doc_id=1,
            doc_name="doc1.pdf",
            chunk_index=0
        )

        result_dict = result.to_dict()

        assert result_dict['chunk_id'] == "chunk1"
        assert result_dict['content'] == "Test content"
        assert result_dict['score'] == 0.85
        assert result_dict['doc_id'] == 1
        assert result_dict['doc_name'] == "doc1.pdf"
        assert result_dict['chunk_index'] == 0
