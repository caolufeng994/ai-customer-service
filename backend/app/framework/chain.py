"""
Chain Framework Primitive
Chain composition for orchestrating multiple components
Implements chain composition similar to LangChain Chain
"""
from abc import ABC, abstractmethod
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class BaseChain(ABC):
    """
    Abstract base class for chains
    Chains compose multiple components into a processing pipeline
    """

    @abstractmethod
    def run(self, **kwargs) -> dict:
        """
        Run the chain

        Args:
            **kwargs: Input parameters

        Returns:
            Output dictionary
        """
        pass


class RAGChain(BaseChain):
    """
    RAG Chain - composes retriever, context builder, prompt builder, and LLM
    Implements the standard RAG pipeline as a reusable unit
    """

    def __init__(
        self,
        retriever,
        context_builder,
        prompt_builder,
        llm,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ):
        """
        Initialize RAG chain

        Args:
            retriever: Retriever instance (from framework/retriever.py)
            context_builder: ContextBuilder instance (from app.rag.context_builder)
            prompt_builder: PromptBuilder instance (from app.rag.prompt_builder)
            llm: LLM instance (from framework/llm.py)
            max_tokens: Maximum tokens for LLM generation
            temperature: Sampling temperature
        """
        self.retriever = retriever
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.llm = llm
        self.max_tokens = max_tokens
        self.temperature = temperature

    def run(
        self,
        query: str,
        kb_id: str = "default",
        history: Optional[List[dict]] = None,
        stream: bool = False
    ) -> dict:
        """
        Run RAG pipeline

        Args:
            query: User query
            kb_id: Knowledge base ID
            history: Conversation history
            stream: Whether to stream response

        Returns:
            Dictionary with content, sources, and metadata
        """
        # Step 1: Retrieve
        retrieval_results = self.retriever.retrieve(query, top_k=8, kb_id=kb_id)

        # Step 2: Build context
        context, sources = self.context_builder.build_context_with_sources(retrieval_results)

        # Step 3: Build prompt
        if context:
            messages = self.prompt_builder.build_prompt(query, context, history)
            finish_reason = "stop"
        else:
            messages = self.prompt_builder.build_fallback_prompt(query)
            finish_reason = "no_context"

        # Step 4: Generate response
        try:
            if stream:
                # Streaming mode
                full_response = ""
                for chunk in self.llm.chat_stream(
                    messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                ):
                    full_response += chunk
            else:
                # Non-streaming mode
                result = self.llm.chat(
                    messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False
                )
                full_response = result.content

            return {
                "content": full_response,
                "sources": sources,
                "finish_reason": finish_reason,
                "retrieval_count": len(retrieval_results),
                "context_length": len(context)
            }

        except Exception as e:
            logger.error(f"RAG chain failed: {e}")
            return {
                "content": "Sorry, I encountered an error while processing your request.",
                "sources": [],
                "finish_reason": "error",
                "error": str(e)
            }


class SequentialChain(BaseChain):
    """
    Sequential Chain - runs multiple chains in sequence
    Output of one chain becomes input to the next
    """

    def __init__(self, chains: List[BaseChain]):
        """
        Initialize sequential chain

        Args:
            chains: List of chains to run in sequence
        """
        self.chains = chains

    def run(self, **kwargs) -> dict:
        """
        Run chains sequentially

        Args:
            **kwargs: Input parameters for first chain

        Returns:
            Output from final chain
        """
        current_output = kwargs

        for i, chain in enumerate(self.chains):
            logger.debug(f"Running chain {i+1}/{len(self.chains)}")
            current_output = chain.run(**current_output)

        return current_output
