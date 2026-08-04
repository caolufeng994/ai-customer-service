"""
Planner Framework Primitive
Intent router for mapping intents to actions
Implements intent-to-target routing similar to LangChain router
Uses unified RouteTarget from app/agent/router to avoid duplication
"""
from app.agent.router import RouteTarget
import logging

logger = logging.getLogger(__name__)


class IntentRouter:
    """
    Intent router that maps user intents to processing targets
    Implements a configurable mapping table for extensibility
    Uses unified RouteTarget enum from app/agent/router
    """

    def __init__(self):
        """Initialize intent router with default mappings"""
        self._intent_map = {
            # Product-related intents -> RAG
            "product_consult": RouteTarget.RAG,
            "pricing": RouteTarget.RAG,
            "features": RouteTarget.RAG,

            # After-sales intents -> RAG
            "refund": RouteTarget.RAG,
            "return": RouteTarget.RAG,
            "warranty": RouteTarget.RAG,

            # Account intents -> RAG
            "account": RouteTarget.RAG,
            "login": RouteTarget.RAG,
            "password": RouteTarget.RAG,

            # Knowledge base intents -> RAG
            "documentation": RouteTarget.RAG,
            "faq": RouteTarget.RAG,

            # Order intents -> RAG (currently, not TOOL as TOOl not implemented)
            "order_query": RouteTarget.RAG,
            "order_status": RouteTarget.RAG,

            # Fallback intents（闲聊/问候/未知 → 直接对话式回答，不检索）
            "chitchat": RouteTarget.DIRECT,
            "greeting": RouteTarget.DIRECT,
            "unknown": RouteTarget.DIRECT,
        }

    def route(self, intent: str) -> RouteTarget:
        """
        Route intent to target

        Args:
            intent: Intent string

        Returns:
            RouteTarget for processing
        """
        target = self._intent_map.get(intent, RouteTarget.DIRECT)
        logger.debug(f"Routed intent '{intent}' to target '{target.value}'")
        return target

    def add_mapping(self, intent: str, target: RouteTarget) -> None:
        """
        Add or update intent mapping

        Args:
            intent: Intent string
            target: Route target
        """
        self._intent_map[intent] = target
        logger.info(f"Added mapping: {intent} -> {target.value}")

    def remove_mapping(self, intent: str) -> None:
        """
        Remove intent mapping

        Args:
            intent: Intent string
        """
        if intent in self._intent_map:
            del self._intent_map[intent]
            logger.info(f"Removed mapping: {intent}")

    def list_mappings(self) -> dict[str, RouteTarget]:
        """List all intent mappings"""
        return self._intent_map.copy()
