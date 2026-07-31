"""
Prompt Builder Module
Builds prompts with system template and context
"""
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Prompt builder for constructing LLM prompts
    This step builds the final prompt with system message, context, and user query
    """
    
    # System template
    SYSTEM_TEMPLATE = """你是一个智能客服助手，负责回答用户关于产品和服务的问题。

请根据以下知识库内容回答用户的问题。如果知识库中没有相关信息，请明确告知用户你无法回答该问题，不要编造信息。

回答要求：
1. 准确、简洁、友好
2. 基于提供的知识库内容
3. 如果信息不足，请说明
4. 使用中文回答"""

    def __init__(self, system_template: Optional[str] = None):
        """
        Initialize prompt builder
        
        Args:
            system_template: Custom system template (uses default if None)
        """
        self.system_template = system_template or self.SYSTEM_TEMPLATE
    
    def build_prompt(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[dict]] = None
    ) -> List[dict]:
        """
        Build prompt for LLM
        
        Args:
            query: User query
            context: Retrieved context
            conversation_history: Previous conversation messages
            
        Returns:
            List of message dictionaries for LLM
        """
        messages = []
        
        # System message
        messages.append({
            "role": "system",
            "content": self.system_template
        })
        
        # Add conversation history (last 5 turns)
        if conversation_history:
            recent_history = conversation_history[-10:]  # Last 10 messages (5 turns)
            messages.extend(recent_history)
        
        # Build user message with context
        if context:
            user_message = f"""知识库内容：
{context}

用户问题：
{query}"""
        else:
            user_message = f"""用户问题：
{query}"""
        
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def build_fallback_prompt(self, query: str) -> List[dict]:
        """
        Build prompt for fallback (no context)
        
        Args:
            query: User query
            
        Returns:
            List of message dictionaries
        """
        messages = [
            {
                "role": "system",
                "content": "你是一个智能客服助手。由于知识库中没有找到相关信息，请礼貌地告知用户你无法回答该问题，并建议用户联系人工客服。"
            },
            {
                "role": "user",
                "content": query
            }
        ]
        
        return messages
