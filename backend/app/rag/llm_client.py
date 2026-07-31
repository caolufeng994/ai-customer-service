"""
LLM Client Module
Abstraction for LLM providers (DashScope and Ollama)
"""
from typing import Iterator, Optional, List
from openai import OpenAI
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM client abstraction supporting multiple providers
    This step handles LLM inference with streaming support
    """
    
    def __init__(self, provider: Optional[str] = None):
        """
        Initialize LLM client
        
        Args:
            provider: LLM provider (dashscope or ollama). Uses config default if None
        """
        self.provider = provider or settings.llm_provider
        
        if self.provider == "dashscope":
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            self.model = settings.dashscope_model
        elif self.provider == "ollama":
            self.client = OpenAI(
                base_url=settings.ollama_base_url,
                api_key="ollama"  # Ollama doesn't require real API key
            )
            self.model = settings.ollama_model
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
        
        logger.info(f"Initialized LLM client: {self.provider} with model {self.model}")
    
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
                    if chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                return full_response
            else:
                return response.choices[0].message.content
                
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM chat stream failed: {e}")
            raise
    
    def fallback_to_ollama(self) -> 'LLMClient':
        """
        Fallback to Ollama if primary provider fails
        
        Returns:
            New LLM client with Ollama provider
        """
        logger.warning("Falling back to Ollama")
        return LLMClient(provider="ollama")
