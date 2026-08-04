"""
LLM Framework Primitive
Abstract base class and implementations for LLM providers
Supports fallback between DashScope and Ollama
"""
from abc import ABC, abstractmethod
from typing import Iterator, List, Optional
from openai import OpenAI
from app.config import settings
import logging
import time

logger = logging.getLogger(__name__)


class LLMResult:
    """LLM response result"""
    def __init__(self, content: str, finish_reason: str = "stop", token_usage: Optional[dict] = None):
        self.content = content
        self.finish_reason = finish_reason
        self.token_usage = token_usage


class BaseLLM(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> LLMResult:
        """
        Chat completion (non-streaming)

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response

        Returns:
            LLMResult with content and metadata
        """
        pass

    @abstractmethod
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
        pass


class DashScopeLLM(BaseLLM):
    """DashScope (Aliyun) LLM implementation"""

    def __init__(self, model: Optional[str] = None):
        """
        Initialize DashScope LLM client

        Args:
            model: Model name (uses config default if None)
        """
        self.model = model or settings.dashscope_model
        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=30.0,
            max_retries=2
        )
        logger.info(f"Initialized DashScopeLLM with model {self.model}")

    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> LLMResult:
        """Chat completion (non-streaming)"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )

            if stream:
                # Streaming mode - collect chunks
                full_response = ""
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        full_response += delta.content
                return LLMResult(content=full_response, finish_reason="stop")
            else:
                return LLMResult(
                    content=response.choices[0].message.content,
                    finish_reason=response.choices[0].finish_reason or "stop",
                    token_usage={
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0
                    } if response.usage else None
                )

        except Exception as e:
            logger.error(f"DashScopeLLM chat failed: {e}")
            raise

    def chat_stream(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Iterator[str]:
        """Chat completion with streaming"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except Exception as e:
            logger.error(f"DashScopeLLM chat stream failed: {e}")
            raise


class OllamaLLM(BaseLLM):
    """Ollama LLM implementation (local fallback)"""

    def __init__(self, model: str = "qwen2:7b"):
        """
        Initialize Ollama LLM client

        Args:
            model: Model name (default: qwen2:7b)
        """
        self.model = model
        try:
            self.client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",  # Ollama doesn't require real API key
                timeout=60.0,
                max_retries=1
            )
            logger.info(f"Initialized OllamaLLM with model {self.model}")
        except Exception as e:
            logger.warning(f"Failed to initialize OllamaLLM: {e}")
            self.client = None

    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> LLMResult:
        """Chat completion (non-streaming)"""
        if not self.client:
            raise RuntimeError("Ollama client not initialized")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )

            if stream:
                full_response = ""
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        full_response += delta.content
                return LLMResult(content=full_response, finish_reason="stop")
            else:
                return LLMResult(
                    content=response.choices[0].message.content,
                    finish_reason=response.choices[0].finish_reason or "stop"
                )

        except Exception as e:
            logger.error(f"OllamaLLM chat failed: {e}")
            raise

    def chat_stream(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Iterator[str]:
        """Chat completion with streaming"""
        if not self.client:
            raise RuntimeError("Ollama client not initialized")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except Exception as e:
            logger.error(f"OllamaLLM chat stream failed: {e}")
            raise


class FallbackLLM(BaseLLM):
    """
    Fallback LLM with automatic switching between providers
    Implements a finite state machine for fallback logic
    """

    def __init__(
        self,
        primary: BaseLLM,
        secondary: Optional[BaseLLM] = None,
        failure_threshold: int = 3,
        recovery_cooldown: int = 60
    ):
        """
        Initialize fallback LLM

        Args:
            primary: Primary LLM provider
            secondary: Secondary/fallback LLM provider
            failure_threshold: Number of consecutive failures before switching
            recovery_cooldown: Seconds to wait before attempting recovery
        """
        self.primary = primary
        self.secondary = secondary or OllamaLLM()
        self.failure_threshold = failure_threshold
        self.recovery_cooldown = recovery_cooldown

        self.primary_ok = True
        self.failure_count = 0
        self.last_failure_time = 0

        logger.info(f"Initialized FallbackLLM: primary={type(primary).__name__}, secondary={type(secondary).__name__}")

    def _should_use_secondary(self) -> bool:
        """        Check if should use secondary provider"""
        current_time = time.time()

        # If primary is marked as failed, check if cooldown period has passed
        if not self.primary_ok:
            if current_time - self.last_failure_time > self.recovery_cooldown:
                # Attempt recovery
                logger.info("Attempting to recover primary provider")
                self.primary_ok = True
                self.failure_count = 0
                return False
            return True

        return False

    def _record_failure(self):
        """        Record a failure and potentially switch providers"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Primary provider failed {self.failure_count} times, switching to secondary")
            self.primary_ok = False

    def _record_success(self, used_primary: bool):
        """
        Record a success and reset failure count
        Only reset failure count when primary succeeds, not when secondary succeeds
        """
        if used_primary:
            # Primary succeeded, reset failure count
            self.failure_count = 0
            logger.debug("Primary provider succeeded, reset failure count")
        else:
            # Secondary succeeded, do NOT reset primary's failure count
            # This allows the threshold to be reached and primary to be marked as failed
            logger.debug("Secondary provider succeeded, keeping primary failure count")

    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> LLMResult:
        """Chat completion with fallback"""
        used_primary = not self._should_use_secondary()
        provider = self.secondary if not used_primary else self.primary

        try:
            result = provider.chat(messages, temperature, max_tokens, stream)
            self._record_success(used_primary)
            return result

        except Exception as e:
            logger.error(f"Provider {type(provider).__name__} failed: {e}")
            if provider == self.primary:
                self._record_failure()
                # Try secondary if primary failed
                if self.secondary:
                    logger.info("Falling back to secondary provider")
                    try:
                        result = self.secondary.chat(messages, temperature, max_tokens, stream)
                        self._record_success(used_primary=False)  # Secondary succeeded, don't reset primary failure count
                        return result
                    except Exception as e2:
                        logger.error(f"Secondary provider also failed: {e2}")
            raise

    def chat_stream(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Iterator[str]:
        """Chat completion with streaming fallback"""
        provider = self.secondary if self._should_use_secondary() else self.primary

        try:
            for chunk in provider.chat_stream(messages, temperature, max_tokens):
                yield chunk
            self._record_success(used_primary=True)

        except Exception as e:
            logger.error(f"Provider {type(provider).__name__} stream failed: {e}")
            if provider == self.primary:
                self._record_failure()
                # Try secondary if primary failed
                if self.secondary:
                    logger.info("Falling back to secondary provider")
                    try:
                        for chunk in self.secondary.chat_stream(messages, temperature, max_tokens):
                            yield chunk
                        self._record_success(used_primary=False)
                        return
                    except Exception as e2:
                        logger.error(f"Secondary provider also failed: {e2}")
            raise
