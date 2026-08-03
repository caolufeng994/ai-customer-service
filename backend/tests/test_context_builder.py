"""
Unit tests for ContextBuilder module
Tests token budget, deduplication, and context building logic
"""
import pytest
from app.rag.context_builder import ContextBuilder
from app.rag.retriever import RetrievalResult


@pytest.fixture
def context_builder():
    """Create context builder instance"""
    return ContextBuilder(max_tokens=2000)


@pytest.fixture
def sample_retrieval_results():
    """Create sample retrieval results for testing"""
    return [
        RetrievalResult(
            chunk_id="chunk1",
            content="This is the first chunk of content about product features.",
            score=0.9,
            doc_id=1,
            doc_name="product_manual.pdf",
            chunk_index=0
        ),
        RetrievalResult(
            chunk_id="chunk2",
            content="This is the second chunk about pricing information.",
            score=0.85,
            doc_id=2,
            doc_name="product_manual.pdf",
            chunk_index=1
        ),
        RetrievalResult(
            chunk_id="chunk3",
            content="This is the third chunk about warranty details.",
            score=0.8,
            doc_id=3,
            doc_name="warranty.pdf",
            chunk_index=0
        )
    ]


class TestContextBuilder:
    """Test cases for ContextBuilder class"""

    def test_build_context_basic(self, context_builder, sample_retrieval_results):
        """Test basic context building"""
        context = context_builder.build_context(sample_retrieval_results)

        assert context is not None
        assert len(context) > 0
        assert "product features" in context
        assert "pricing information" in context

    def test_build_context_with_sources(self, context_builder, sample_retrieval_results):
        """Test context building with source metadata"""
        context, sources = context_builder.build_context_with_sources(sample_retrieval_results)

        assert context is not None
        assert sources is not None
        assert len(sources) == 3
        assert sources[0]['doc_name'] == "product_manual.pdf"
        assert sources[0]['score'] == 0.9

    def test_build_context_token_budget(self, context_builder):
        """Test that context respects token budget"""
        # Create many large chunks
        large_chunks = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                content="A" * 500,  # Large content
                score=0.9 - i * 0.05,
                doc_id=1,
                doc_name="doc.pdf",
                chunk_index=i
            )
            for i in range(10)
        ]

        context = context_builder.build_context(large_chunks)

        # Approximate token check (1 token ≈ 2 chars)
        estimated_tokens = len(context) // 2
        assert estimated_tokens <= context_builder.max_tokens * 1.1  # Allow 10% overflow

    def test_build_context_deduplication(self, context_builder):
        """Test content deduplication"""
        # Create duplicate chunks
        duplicate_chunks = [
            RetrievalResult(
                chunk_id="chunk1",
                content="This is duplicate content.",
                score=0.9,
                doc_id=1,
                doc_name="doc1.pdf",
                chunk_index=0
            ),
            RetrievalResult(
                chunk_id="chunk2",
                content="This is duplicate content.",  # Same content
                score=0.85,
                doc_id=2,
                doc_name="doc2.pdf",
                chunk_index=0
            ),
            RetrievalResult(
                chunk_id="chunk3",
                content="This is unique content.",
                score=0.8,
                doc_id=3,
                doc_name="doc3.pdf",
                chunk_index=0
            )
        ]

        context = context_builder.build_context(duplicate_chunks)

        # Should only contain unique content once
        assert context.count("This is duplicate content.") == 1
        assert "This is unique content." in context

    def test_build_context_empty_results(self, context_builder):
        """Test handling of empty retrieval results"""
        context = context_builder.build_context([])

        assert context == ""

    def test_build_context_sorting_by_score(self, context_builder):
        """Test that results are sorted by similarity score"""
        # Create unsorted results
        unsorted_chunks = [
            RetrievalResult(
                chunk_id="chunk3",
                content="Low score content.",
                score=0.7,
                doc_id=1,
                doc_name="doc.pdf",
                chunk_index=2
            ),
            RetrievalResult(
                chunk_id="chunk1",
                content="High score content.",
                score=0.9,
                doc_id=1,
                doc_name="doc.pdf",
                chunk_index=0
            ),
            RetrievalResult(
                chunk_id="chunk2",
                content="Medium score content.",
                score=0.8,
                doc_id=1,
                doc_name="doc.pdf",
                chunk_index=1
            )
        ]

        context = context_builder.build_context(unsorted_chunks)

        # High score content should appear first
        assert context.index("High score content.") < context.index("Medium score content.")
        assert context.index("Medium score content.") < context.index("Low score content.")
