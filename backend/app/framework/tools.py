"""
Tools Framework Primitive
Abstract base class and registry for tool functions
Implements tool protocol similar to LangChain BaseTool
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Abstract base class for tools
    A tool is a function that can be called by an LLM to perform actions
    """

    name: str = ""
    description: str = ""
    args_schema: Dict[str, Any] = {}

    @abstractmethod
    def run(self, **kwargs) -> str:
        """
        Execute the tool

        Args:
            **kwargs: Tool arguments

        Returns:
            Tool output as string
        """
        pass

    def get_description(self) -> str:
        """Get tool description for LLM"""
        return f"{self.name}: {self.description}"


class ToolRegistry:
    """
    Registry for managing available tools
    Provides tool discovery and description generation for LLM prompts
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool

        Args:
            tool: Tool instance to register
        """
        if not tool.name:
            raise ValueError("Tool must have a name")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """List all registered tools"""
        return list(self._tools.values())

    def describe_for_prompt(self) -> str:
        """
        Generate tool descriptions for LLM prompt

        Returns:
            Formatted string describing all tools
        """
        if not self._tools:
            return "No tools available."

        descriptions = []
        for tool in self._tools.values():
            desc = f"- {tool.name}: {tool.description}"
            if tool.args_schema:
                desc += f" (args: {tool.args_schema})"
            descriptions.append(desc)

        return "Available tools:\n" + "\n".join(descriptions)


class DemoTool(BaseTool):
    """Demo tool for testing"""

    name = "get_current_time"
    description = "Get the current date and time"
    args_schema = {}

    def run(self, **kwargs) -> str:
        """Get current time"""
        from datetime import datetime
        return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


class QueryOrderTool(BaseTool):
    """Demo tool for querying order status"""

    name = "query_order_status"
    description = "Query the status of an order by order ID"
    args_schema = {"order_id": "string (required)"}

    def run(self, **kwargs) -> str:
        """Query order status"""
        order_id = kwargs.get("order_id")
        if not order_id:
            return "Error: order_id is required"

        # Mock implementation - in real system, query database
        return f"Order {order_id} status: Shipped (2024-01-15)"
