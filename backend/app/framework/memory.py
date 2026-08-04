"""
Memory Framework Primitive
Abstract base class and implementations for conversation memory
Implements memory management similar to LangChain BaseMemory
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseMemory(ABC):
    """
    Abstract base class for memory
    Manages conversation history for multi-turn dialogue
    """

    @abstractmethod
    def add_user(self, msg: str) -> None:
        """Add user message to memory"""
        pass

    @abstractmethod
    def add_ai(self, msg: str) -> None:
        """Add AI message to memory"""
        pass

    @abstractmethod
    def load_context(self) -> str:
        """Load context as string for prompt"""
        pass

    @abstractmethod
    def token_usage(self) -> int:
        """Estimate token usage of current memory"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all memory"""
        pass


class WindowMemory(BaseMemory):
    """
    Window-based memory - keeps only the last N messages
    Simple and efficient for most use cases
    """

    def __init__(self, window_size: int = 10):
        """
        Initialize window memory

        Args:
            window_size: Number of messages to keep (default: 10)
        """
        self.window_size = window_size
        self._messages: List[dict] = []

    def add_user(self, msg: str) -> None:
        """Add user message"""
        self._messages.append({"role": "user", "content": msg})
        self._trim()

    def add_ai(self, msg: str) -> None:
        """Add AI message"""
        self._messages.append({"role": "assistant", "content": msg})
        self._trim()

    def load_context(self) -> str:
        """Load context as string"""
        if not self._messages:
            return ""

        context_parts = []
        for msg in self._messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")

        return "\n".join(context_parts)

    def token_usage(self) -> int:
        """Estimate token usage (1 token ≈ 4 characters for Chinese)"""
        total_chars = sum(len(msg["content"]) for msg in self._messages)
        return total_chars // 4

    def clear(self) -> None:
        """Clear all memory"""
        self._messages.clear()

    def _trim(self) -> None:
        """Trim to window size"""
        if len(self._messages) > self.window_size:
            self._messages = self._messages[-self.window_size:]

    def get_messages(self) -> List[dict]:
        """Get all messages"""
        return self._messages.copy()


class CompactionMemory(BaseMemory):
    """
    Compaction-based memory - summarizes old messages when token budget exceeded
    More sophisticated than window memory for long conversations
    """

    def __init__(self, max_tokens: int = 2000, keep_recent: int = 4):
        """
        Initialize compaction memory

        Args:
            max_tokens: Maximum token budget before compaction
            keep_recent: Number of recent messages to keep without summarization
        """
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self._messages: List[dict] = []
        self._summary: Optional[str] = None

    def add_user(self, msg: str) -> None:
        """Add user message"""
        self._messages.append({"role": "user", "content": msg})
        self._check_compaction()

    def add_ai(self, msg: str) -> None:
        """Add AI message"""
        self._messages.append({"role": "assistant", "content": msg})
        self._check_compaction()

    def load_context(self) -> str:
        """Load context as string"""
        parts = []

        # Add summary if exists
        if self._summary:
            parts.append(f"Conversation Summary: {self._summary}")

        # Add recent messages
        for msg in self._messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}")

        return "\n".join(parts)

    def token_usage(self) -> int:
        """Estimate token usage"""
        total_chars = sum(len(msg["content"]) for msg in self._messages)
        if self._summary:
            total_chars += len(self._summary)
        return total_chars // 4

    def clear(self) -> None:
        """Clear all memory"""
        self._messages.clear()
        self._summary = None

    def _check_compaction(self) -> None:
        """Check if compaction is needed"""
        if self.token_usage() > self.max_tokens and len(self._messages) > self.keep_recent:
            logger.info("Token budget exceeded, triggering compaction")
            self._compact()

    def _compact(self) -> None:
        """
        Compact old messages into summary
        NOTE: This is a stub implementation that uses simple truncation.
        A production implementation would use LLM-based summarization.
        """
        if len(self._messages) <= self.keep_recent:
            return

        # Messages to summarize (all except recent)
        old_messages = self._messages[:-self.keep_recent]
        recent_messages = self._messages[-self.keep_recent:]

        # Build summary text
        summary_text = "\n".join([
            f"{msg['role']}: {msg['content']}" for msg in old_messages
        ])

        # Stub: use simple truncation (not true summarization)
        # In production, this should call an LLM to generate a proper summary
        self._summary = summary_text[:500] + "..." if len(summary_text) > 500 else summary_text

        # Keep only recent messages
        self._messages = recent_messages

        logger.warning(f"Compacted {len(old_messages)} messages using truncation stub (not LLM summarization)")


class QueryRewriter:
    """
    Query rewriter for multi-turn dialogue
    Resolves pronouns and references in follow-up questions
    Similar to LangChain's condense_question
    """

    @staticmethod
    def rewrite(history: List[dict], current_query: str) -> str:
        """
        Rewrite current query to be standalone by resolving references

        Args:
            history: Conversation history (list of {role, content})
            current_query: Current user query

        Returns:
            Rewritten standalone query
        """
        # If no history, return as-is
        if not history:
            return current_query

        # Get last user message
        last_user_msg = None
        for msg in reversed(history):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break

        # If no previous user message, return as-is
        if not last_user_msg:
            return current_query

        # Simple heuristic: if current query is short and contains pronouns
        # combine with previous question
        pronouns = ["它", "这个", "那个", "这", "那", "它们", "这些", "那些"]
        contains_pronoun = any(p in current_query for p in pronouns)

        if contains_pronoun and len(current_query) < 20:
            rewritten = f"{last_user_msg} {current_query}"
            logger.debug(f"Rewrote query: '{current_query}' -> '{rewritten}'")
            return rewritten

        return current_query
