"""
LLM Client Module
Legacy wrapper for backward compatibility
Uses the new framework/llm.py BaseLLM abstraction
"""
from typing import Iterator, Optional, List
from app.framework.llm import DashScopeLLM, FallbackLLM, OllamaLLM
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM client wrapper for backward compatibility
    Delegates to framework/llm.py BaseLLM implementations
    """

    def __init__(self, provider: Optional[str] = None):
        """
        Initialize LLM client using framework abstraction

        Args:
            provider: LLM provider (dashscope). Uses config default if None
        """
        self.provider = provider or settings.llm_provider

        # Use framework abstraction with fallback
        if self.provider == "dashscope":
            primary = DashScopeLLM()
            secondary = OllamaLLM()
            self._llm = FallbackLLM(primary=primary, secondary=secondary)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(f"Initialized LLM client using framework: {self.provider}")

    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> str:
        """
        Chat completion (non-streaming)

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response

        Returns:
            Generated response text
        """
        try:
            result = self._llm.chat(messages, temperature, max_tokens, stream)
            return result.content
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            raise

    def chat_stream(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Iterator[str]:
        """
        Chat completion with streaming

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Response text chunks
        """
        try:
            for chunk in self._llm.chat_stream(messages, temperature, max_tokens):
                yield chunk
        except Exception as e:
            logger.error(f"LLM chat stream failed: {e}")
            raise
    
