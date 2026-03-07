"""Claude AI assistant layer.

Wraps the Anthropic API for conversation-style responses.
"""

import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


class ClaudeAssistant:
    """Manages Claude API calls for the bot."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "You are a helpful assistant responding via iMessage. Keep responses concise and conversational.",
        max_tokens: int = 1024,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    def respond(self, messages: list[dict], system_prompt: Optional[str] = None) -> str:
        """Get a response from Claude given a conversation history.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."} dicts.
            system_prompt: Override the default system prompt for this call.

        Returns:
            Claude's response text.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or self.system_prompt,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            return "Sorry, I'm having trouble responding right now. Please try again."
