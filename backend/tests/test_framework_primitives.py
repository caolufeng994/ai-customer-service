"""
Unit tests for framework primitives
Tests critical primitives: QueryRewriter, verify_citations, FallbackLLM, ReActAgent
"""
from app.framework.memory import QueryRewriter, WindowMemory, CompactionMemory
from app.rag.prompt_builder import PromptBuilder
from app.framework.llm import DashScopeLLM, OllamaLLM, FallbackLLM, LLMResult
from unittest.mock import Mock


class TestQueryRewriter:
    """Test QueryRewriter for multi-turn dialogue"""

    def test_rewrite_with_pronouns(self):
        """Test rewriting queries with pronouns"""
        history = [
            {"role": "user", "content": "会员有什么折扣？"},
            {"role": "assistant", "content": "会员享受9折优惠。"}
        ]
        current_query = "那退货呢？"

        rewritten = QueryRewriter.rewrite(history, current_query)

        # Should combine with previous user message
        assert "会员有什么折扣" in rewritten
        assert "退货呢" in rewritten

    def test_rewrite_without_pronouns(self):
        """Test that queries without pronouns are not modified"""
        history = [
            {"role": "user", "content": "会员有什么折扣？"},
            {"role": "assistant", "content": "会员享受9折优惠。"}
        ]
        current_query = "退款政策是什么？"

        rewritten = QueryRewriter.rewrite(history, current_query)

        # Should remain unchanged
        assert rewritten == current_query

    def test_rewrite_empty_history(self):
        """Test rewriting with empty history"""
        history = []
        current_query = "会员有什么折扣？"

        rewritten = QueryRewriter.rewrite(history, current_query)

        # Should remain unchanged
        assert rewritten == current_query


class TestVerifyCitations:
    """Test citation verification in PromptBuilder"""

    def test_verify_valid_citations(self):
        """Test verification of valid citations"""
        prompt_builder = PromptBuilder()

        context = "[K1] Content 1\n\n[K2] Content 2"
        response = "根据[K1]和[K2]的信息，答案是..."

        is_valid, invalid = prompt_builder.verify_citations(response, context)

        assert is_valid is True
        assert len(invalid) == 0

    def test_verify_invalid_citations(self):
        """Test detection of invalid citations"""
        prompt_builder = PromptBuilder()

        context = "[K1] Content 1\n\n[K2] Content 2"
        response = "根据[K1]和[K5]的信息，答案是..."

        is_valid, invalid = prompt_builder.verify_citations(response, context)

        assert is_valid is False
        assert "K5" in invalid

    def test_verify_no_citations(self):
        """Test that responses without citations are valid"""
        prompt_builder = PromptBuilder()

        context = "[K1] Content 1"
        response = "答案是..."

        is_valid, invalid = prompt_builder.verify_citations(response, context)

        assert is_valid is True
        assert len(invalid) == 0

    def test_verify_out_of_range_citation(self):
        """Test detection of out-of-range citations"""
        prompt_builder = PromptBuilder()

        context = "[K1] Content 1"
        response = "根据[K0]的信息，答案是..."

        is_valid, invalid = prompt_builder.verify_citations(response, context)

        assert is_valid is False
        assert "K0" in invalid


class TestWindowMemory:
    """Test WindowMemory implementation"""

    def test_window_memory_basic(self):
        """Test basic window memory operations"""
        memory = WindowMemory(window_size=4)

        memory.add_user("Hello")
        memory.add_ai("Hi there")
        memory.add_user("How are you?")

        context = memory.load_context()

        assert "Hello" in context
        assert "Hi there" in context
        assert "How are you?" in context

    def test_window_memory_truncation(self):
        """Test that memory truncates to window size (keeps last N messages)"""
        memory = WindowMemory(window_size=2)

        memory.add_user("User1")
        memory.add_ai("AI1")
        memory.add_user("User2")
        memory.add_ai("AI2")
        memory.add_user("User3")

        context = memory.load_context()

        # Should only keep last 2 messages (AI2 and User3)
        assert "User1" not in context
        assert "AI1" not in context
        assert "User2" not in context
        assert "AI2" in context
        assert "User3" in context

    def test_window_memory_clear(self):
        """Test clearing memory"""
        memory = WindowMemory(window_size=4)

        memory.add_user("Hello")
        memory.clear()

        context = memory.load_context()

        assert context == ""


class TestCompactionMemory:
    """Test CompactionMemory implementation"""

    def test_compaction_memory_basic(self):
        """Test basic compaction memory operations"""
        memory = CompactionMemory(max_tokens=100, keep_recent=2)

        memory.add_user("User1")
        memory.add_ai("AI1")

        context = memory.load_context()

        assert "User1" in context
        assert "AI1" in context

    def test_compaction_memory_compaction(self):
        """Test that memory compacts when token budget exceeded"""
        memory = CompactionMemory(max_tokens=10, keep_recent=2)

        # Add many messages to trigger compaction
        for i in range(10):
            memory.add_user(f"User message {i}")
            memory.add_ai(f"AI response {i}")

        # Should have triggered compaction
        assert memory._summary is not None

    def test_compaction_memory_clear(self):
        """Test clearing compaction memory"""
        memory = CompactionMemory(max_tokens=100, keep_recent=2)

        memory.add_user("Hello")
        memory.clear()

        context = memory.load_context()

        assert context == ""
        assert memory._summary is None


class TestFallbackLLM:
    """Test FallbackLLM switching logic"""

    def test_fallback_primary_success(self):
        """Test that primary provider is used when successful"""
        primary = Mock(spec=DashScopeLLM)
        primary.chat.return_value = LLMResult(content="Response from primary")

        secondary = Mock(spec=OllamaLLM)

        fallback = FallbackLLM(primary=primary, secondary=secondary)

        result = fallback.chat([{"role": "user", "content": "test"}])

        assert result.content == "Response from primary"
        primary.chat.assert_called_once()
        secondary.chat.assert_not_called()

    def test_fallback_secondary_on_failure(self):
        """Test that secondary provider is used when primary fails"""
        primary = Mock(spec=DashScopeLLM)
        primary.chat.side_effect = Exception("Primary failed")

        secondary = Mock(spec=OllamaLLM)
        secondary.chat.return_value = LLMResult(content="Response from secondary")

        fallback = FallbackLLM(primary=primary, secondary=secondary)

        result = fallback.chat([{"role": "user", "content": "test"}])

        assert result.content == "Response from secondary"
        primary.chat.assert_called_once()
        secondary.chat.assert_called_once()

    def test_fallback_failure_threshold(self):
        """Test that provider switches after failure threshold"""
        primary = Mock(spec=DashScopeLLM)
        primary.chat.side_effect = Exception("Primary failed")

        secondary = Mock(spec=OllamaLLM)
        secondary.chat.return_value = LLMResult(content="Response from secondary")

        fallback = FallbackLLM(primary=primary, secondary=secondary, failure_threshold=3)

        # Fail primary 3 times
        for _ in range(3):
            fallback.chat([{"role": "user", "content": "test"}])

        # After threshold, should use secondary directly
        primary.chat.reset_mock()
        secondary.chat.reset_mock()

        result = fallback.chat([{"role": "user", "content": "test"}])

        assert result.content == "Response from secondary"
        primary.chat.assert_not_called()
        secondary.chat.assert_called_once()


class TestLLMResult:
    """Test LLMResult dataclass"""

    def test_llm_result_creation(self):
        """Test LLMResult creation"""
        result = LLMResult(content="Test response", finish_reason="stop")

        assert result.content == "Test response"
        assert result.finish_reason == "stop"
        # token_usage defaults to None when not provided
        assert result.token_usage is None

    def test_llm_result_with_usage(self):
        """Test LLMResult with token usage"""
        usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        result = LLMResult(content="Test", finish_reason="stop", token_usage=usage)

        assert result.token_usage == usage
        assert result.token_usage["total_tokens"] == 30
