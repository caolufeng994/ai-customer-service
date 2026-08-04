"""
Agent Framework Primitive
Abstract base class and ReAct implementation
Implements agent orchestration similar to LangChain AgentExecutor
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import re
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """Parsed action from LLM response"""
    name: str
    args: Dict[str, Any]


@dataclass
class Step:
    """Single reasoning step"""
    thought: str
    action: Optional[Action]
    observation: Optional[str]


@dataclass
class AgentOutput:
    """Agent execution result"""
    final_answer: str
    steps: List[Step]
    success: bool


class BaseAgent(ABC):
    """
    Abstract base class for agents
    Orchestrates tool use and reasoning
    """

    @abstractmethod
    def run(self, query: str, **kwargs) -> AgentOutput:
        """
        Run agent on a query

        Args:
            query: User query
            **kwargs: Additional parameters

        Returns:
            AgentOutput with final answer and reasoning steps
        """
        pass


class ReActAgent(BaseAgent):
    """
    ReAct (Reasoning + Acting) Agent
    Implements linear Thought→Action→Observation loop
    """

    def __init__(
        self,
        llm,
        tool_registry,
        max_steps: int = 5,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize ReAct agent

        Args:
            llm: LLM instance (from framework/llm.py)
            tool_registry: ToolRegistry instance
            max_steps: Maximum reasoning steps
            system_prompt: Custom system prompt
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps

        self.system_prompt = system_prompt or self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        """Default system prompt for ReAct"""
        return """You are a helpful assistant with access to tools. Follow this format:

Thought: [your reasoning about what to do]
Action: [tool name]
Action Input: [tool arguments in JSON format]
Observation: [tool output]
... (repeat as needed)
Thought: [I know the final answer]
Final Answer: [your final answer]

Available tools:
{tools}

When you have enough information to answer the user's question, provide the Final Answer directly."""

    def run(self, query: str, **kwargs) -> AgentOutput:
        """
        Run ReAct loop

        Args:
            query: User query
            **kwargs: Additional parameters

        Returns:
            AgentOutput with reasoning steps and final answer
        """
        steps = []

        for step_num in range(self.max_steps):
            # Build prompt with current state (only include original query + steps)
            # Don't include current_query which duplicates observations
            prompt = self._build_prompt(query, steps)

            # Get LLM response
            try:
                response = self.llm.chat([{"role": "user", "content": prompt}], stream=False)
                thought_text = response.content
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                return AgentOutput(
                    final_answer="Sorry, I encountered an error while processing your request.",
                    steps=steps,
                    success=False
                )

            # Parse response
            action = self._parse_action(thought_text)

            if action is None:
                # No action - treat as final answer
                final_answer = self._extract_final_answer(thought_text)
                steps.append(Step(thought=thought_text, action=None, observation=None))
                return AgentOutput(final_answer=final_answer, steps=steps, success=True)

            # Execute action
            tool = self.tool_registry.get(action.name)
            if not tool:
                observation = f"Error: Tool '{action.name}' not found"
            else:
                try:
                    observation = tool.run(**action.args)
                    # Truncate observation to prevent prompt explosion
                    observation = self._truncate_observation(observation, max_length=500)
                except Exception as e:
                    observation = f"Error: {str(e)}"

            steps.append(Step(thought=thought_text, action=action, observation=observation))

        # Max steps reached
        return AgentOutput(
            final_answer="I reached the maximum number of reasoning steps without finding a final answer.",
            steps=steps,
            success=False
        )

    def _build_prompt(self, query: str, steps: List[Step]) -> str:
        """Build prompt with query and conversation history"""
        tools_desc = self.tool_registry.describe_for_prompt()

        prompt = self.system_prompt.replace("{tools}", tools_desc)
        prompt += f"\n\nQuestion: {query}\n"

        # Add previous steps
        for step in steps:
            prompt += f"Thought: {step.thought}\n"
            if step.action:
                prompt += f"Action: {step.action.name}\n"
                prompt += f"Action Input: {json.dumps(step.args, ensure_ascii=False)}\n"
                prompt += f"Observation: {step.observation}\n"

        prompt += "Thought:"
        return prompt

    def _parse_action(self, text: str) -> Optional[Action]:
        """
        Parse action from LLM response

        Args:
            text: LLM response text

        Returns:
            Action object or None if no action found
        """
        # Try to extract "Action: tool_name" pattern
        action_match = re.search(r"Action:\s*(\w+)", text, re.IGNORECASE)
        if not action_match:
            return None

        tool_name = action_match.group(1)

        # Try to extract "Action Input: {...}" pattern
        # Use greedy matching to handle nested JSON properly
        input_match = re.search(r"Action Input:\s*(\{.*\})", text, re.IGNORECASE | re.DOTALL)
        if input_match:
            try:
                args = json.loads(input_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse action input JSON: {e}")
                args = {}
        else:
            args = {}

        return Action(name=tool_name, args=args)

    def _truncate_observation(self, observation: str, max_length: int = 500) -> str:
        """
        Truncate observation token to prevent prompt explosion

        Args:
            observation: Tool output
            max_length: Maximum length

        Returns:
            Truncated observation
        """
        if len(observation) <= max_length:
            return observation
        return observation[:max_length] + "..."

    def _extract_final_answer(self, text: str) -> str:
        """
        Extract final answer from LLM response

        Args:
            text: LLM response text

        Returns:
            Final answer string
        """
        # Try to extract "Final Answer: ..." pattern
        final_match = re.search(r"Final Answer:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if final_match:
            return final_match.group(1).strip()

        # Fallback: return entire text
        return text.strip()
