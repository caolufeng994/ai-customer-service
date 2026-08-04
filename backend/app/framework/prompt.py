"""
Prompt Framework Primitive
Simple template engine for prompt construction
Implements prompt template similar to LangChain PromptTemplate
"""
import logging

logger = logging.getLogger(__name__)


class PromptTemplate:
    """
    Simple prompt template engine
    Supports {variable} substitution with safe defaults
    """

    def __init__(self, template: str):
        """
        Initialize prompt template

        Args:
            template: Template string with {variable} placeholders
        """
        self.template = template

    def render(self, **kwargs) -> str:
        """
        Render template with provided variables

        Args:
            **kwargs: Variable values

        Returns:
            Rendered prompt string
        """
        try:
            # Use str.format_map with a custom dict that returns empty string for missing keys
            class SafeDict(dict):
                def __missing__(self, key):
                    logger.warning(f"Missing variable in template: {key}")
                    return ""

            return self.template.format_map(SafeDict(kwargs))

        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            # Fallback: return template with variables replaced by empty strings
            result = self.template
            for key, value in kwargs.items():
                result = result.replace(f"{{{key}}}", str(value))
            return result

    @staticmethod
    def from_messages(messages: list[dict]) -> str:
        """
        Convert message list to single prompt string

        Args:
            messages: List of {role, content} dictionaries

        Returns:
            Combined prompt string
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")

        return "\n\n".join(parts)
